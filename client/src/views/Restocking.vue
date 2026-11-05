<template>
  <div class="restocking">
    <div class="page-header">
      <h2>Restocking</h2>
      <p>Set a budget, review recommended purchases for forecasted shortfalls, and place a restock order.</p>
    </div>

    <div class="card">
      <div class="card-header">
        <h3 class="card-title">Budget</h3>
        <span class="budget-readout">{{ currencySymbol }}{{ budget.toLocaleString() }}</span>
      </div>
      <input
        v-model.number="budget"
        type="range"
        class="budget-slider"
        :min="BUDGET_MIN"
        :max="BUDGET_MAX"
        :step="BUDGET_STEP"
        aria-label="Restocking budget"
        @input="onBudgetInput"
      />
      <div class="slider-scale">
        <span>{{ currencySymbol }}{{ BUDGET_MIN.toLocaleString() }}</span>
        <span>{{ currencySymbol }}{{ BUDGET_MAX.toLocaleString() }}</span>
      </div>
    </div>

    <div v-if="submitSuccess" class="notice success" role="status">
      <span>
        Order <strong>{{ submitSuccess.order_number }}</strong> placed. Expected delivery:
        <strong>{{ formatDate(submitSuccess.expected_delivery) }}</strong>.
      </span>
      <button type="button" class="link-button" @click="submitSuccess = null">Dismiss</button>
    </div>
    <div v-if="submitError" class="notice danger" role="alert">
      <span>{{ submitError }}</span>
      <button type="button" class="link-button" @click="submitError = null">Dismiss</button>
    </div>

    <div v-if="loading" class="loading">Loading recommendations...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">Selected Total</div>
          <div class="stat-value">{{ currencySymbol }}{{ selectedTotal.toLocaleString() }}</div>
        </div>
        <div :class="['stat-card', overBudget ? 'danger' : 'success']">
          <div class="stat-label">Remaining Budget</div>
          <div class="stat-value">{{ currencySymbol }}{{ remaining.toLocaleString() }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">Longest Lead Time</div>
          <div class="stat-value">{{ longestLeadTime }} days</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Items Selected</div>
          <div class="stat-value">{{ selectedRows.length }} / {{ rows.length }}</div>
        </div>
      </div>

      <div class="card" :class="{ refreshing }">
        <div class="card-header">
          <h3 class="card-title">Recommended Purchases ({{ rows.length }})</h3>
          <button
            type="button"
            class="place-order"
            :disabled="!canSubmit"
            @click="submitOrder"
          >
            {{ submitting ? 'Placing order...' : 'Place Order' }}
          </button>
        </div>

        <p v-if="overBudget" class="hint danger-text">
          Selected total exceeds the budget. Reduce quantities or deselect items.
        </p>
        <p v-else-if="hasInvalidQuantity" class="hint danger-text">
          Enter a quantity between 1 and the item shortfall for every selected item.
        </p>

        <div v-if="rows.length === 0" class="empty">
          No items can be recommended within this budget. Increase the budget to see recommendations.
        </div>
        <div v-else class="table-container">
          <table class="restock-table">
            <thead>
              <tr>
                <th class="col-check"><span class="sr-only">Select</span></th>
                <th>SKU</th>
                <th>Name</th>
                <th class="num">On Hand</th>
                <th class="num">Forecast</th>
                <th class="num">Shortfall</th>
                <th class="num">Unit Cost</th>
                <th class="num">Lead Time</th>
                <th class="num col-qty">Quantity</th>
                <th class="num">Line Cost</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.sku" :class="{ deselected: !row.selected }">
                <td class="col-check">
                  <input
                    v-model="row.selected"
                    type="checkbox"
                    :aria-label="`Select ${row.sku}`"
                  />
                </td>
                <td><strong>{{ row.sku }}</strong></td>
                <td>{{ translateProductName(row.name) }}</td>
                <td class="num">{{ row.quantity_on_hand.toLocaleString() }}</td>
                <td class="num">{{ row.forecasted_demand.toLocaleString() }}</td>
                <td class="num">
                  <span class="badge danger">{{ row.shortfall.toLocaleString() }}</span>
                </td>
                <td class="num">{{ currencySymbol }}{{ formatMoney(row.unit_cost) }}</td>
                <td class="num">{{ row.lead_time_days }} days</td>
                <td class="num col-qty">
                  <input
                    v-model.number="row.quantity"
                    type="number"
                    class="qty-input"
                    min="1"
                    :max="row.shortfall"
                    step="1"
                    :aria-label="`Quantity for ${row.sku}`"
                    @change="onQuantityChange(row)"
                  />
                </td>
                <td class="num">
                  <strong>{{ currencySymbol }}{{ formatMoney(lineCost(row)) }}</strong>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

const BUDGET_MIN = 0
const BUDGET_MAX = 50000
const BUDGET_STEP = 250
const DEBOUNCE_MS = 250

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, currentLocale, translateProductName } = useI18n()

    const currencySymbol = computed(() => (currentCurrency.value === 'JPY' ? '¥' : '$'))

    const budget = ref(10000)
    const rows = ref([])
    const loading = ref(true) // first load only; later reloads use `refreshing`
    const refreshing = ref(false)
    const error = ref(null)
    const submitting = ref(false)
    const submitSuccess = ref(null)
    const submitError = ref(null)

    let debounceTimer = null
    let requestSeq = 0 // incremented per request so stale responses can be ignored

    // Money is handled in cents to avoid floating point drift in totals.
    const toCents = (value) => Math.round(Number(value) * 100)

    const isValidQty = (row) =>
      Number.isInteger(row.quantity) && row.quantity >= 1 && row.quantity <= row.shortfall

    const lineCost = (row) => (isValidQty(row) ? (row.quantity * toCents(row.unit_cost)) / 100 : 0)

    const formatMoney = (value) =>
      Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

    const formatDate = (dateString) => {
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return dateString || ''
      return date.toLocaleDateString(currentLocale.value === 'ja' ? 'ja-JP' : 'en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      })
    }

    const selectedRows = computed(() => rows.value.filter(r => r.selected))

    const hasInvalidQuantity = computed(() => selectedRows.value.some(r => !isValidQty(r)))

    const selectedTotal = computed(
      () => selectedRows.value.reduce((sum, r) => sum + (isValidQty(r) ? r.quantity * toCents(r.unit_cost) : 0), 0) / 100
    )

    const remaining = computed(() => (toCents(budget.value) - toCents(selectedTotal.value)) / 100)
    const overBudget = computed(() => remaining.value < 0)

    const longestLeadTime = computed(() =>
      selectedRows.value.reduce((max, r) => Math.max(max, r.lead_time_days), 0)
    )

    const canSubmit = computed(
      () => selectedRows.value.length > 0 && !overBudget.value && !hasInvalidQuantity.value && !submitting.value
    )

    // Merge a fresh recommendation list into existing rows. A user's edited
    // quantity/selection is kept only if the edit still fits the new
    // recommendation (<= recommended_qty, i.e. within the new budget);
    // otherwise the row resets to the server recommendation.
    const mergeRecommendations = (items) => {
      const previous = new Map(rows.value.map(r => [r.sku, r]))
      rows.value = items
        .filter(item => item.recommended_qty > 0)
        .map(item => {
          const prev = previous.get(item.sku)
          const keepEdit = prev && prev.edited && isValidQty(prev) && prev.quantity <= item.recommended_qty
          return {
            ...item,
            selected: prev ? prev.selected : true,
            quantity: keepEdit ? prev.quantity : item.recommended_qty,
            edited: !!keepEdit
          }
        })
    }

    const loadRecommendations = async () => {
      const seq = ++requestSeq
      const requestedBudget = budget.value
      refreshing.value = true
      try {
        const data = await api.getRestockRecommendations(requestedBudget)
        if (seq !== requestSeq) return // a newer request superseded this one
        mergeRecommendations(data.items || [])
        error.value = null
      } catch (err) {
        if (seq !== requestSeq) return
        error.value = 'Failed to load recommendations: ' + err.message
      } finally {
        if (seq === requestSeq) {
          loading.value = false
          refreshing.value = false
        }
      }
    }

    const onBudgetInput = () => {
      clearTimeout(debounceTimer)
      debounceTimer = setTimeout(loadRecommendations, DEBOUNCE_MS)
    }

    // Clamp typed quantities into the valid range and mark the row as user-edited.
    const onQuantityChange = (row) => {
      const parsed = Math.round(Number(row.quantity))
      row.quantity = Number.isFinite(parsed) && parsed >= 1 ? Math.min(parsed, row.shortfall) : 1
      row.edited = true
    }

    const submitOrder = async () => {
      if (!canSubmit.value) return
      submitting.value = true
      submitError.value = null
      submitSuccess.value = null
      try {
        const order = await api.submitRestockOrder({
          budget: budget.value, // always the slider budget, not the selected total
          items: selectedRows.value.map(r => ({ sku: r.sku, quantity: r.quantity }))
        })
        submitSuccess.value = order
        // Discard edits so the refreshed list reflects fresh recommendations.
        rows.value = []
        await loadRecommendations()
      } catch (err) {
        submitError.value = err.response?.data?.detail || err.message || 'Failed to place order'
        if (typeof submitError.value !== 'string') submitError.value = JSON.stringify(submitError.value)
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadRecommendations)
    onBeforeUnmount(() => {
      clearTimeout(debounceTimer)
      requestSeq++ // drop any in-flight response
    })

    return {
      t,
      BUDGET_MIN,
      BUDGET_MAX,
      BUDGET_STEP,
      currencySymbol,
      budget,
      rows,
      loading,
      refreshing,
      error,
      submitting,
      submitSuccess,
      submitError,
      selectedRows,
      selectedTotal,
      remaining,
      overBudget,
      hasInvalidQuantity,
      longestLeadTime,
      canSubmit,
      lineCost,
      formatMoney,
      formatDate,
      onBudgetInput,
      onQuantityChange,
      submitOrder,
      translateProductName
    }
  }
}
</script>

<style scoped>
.budget-readout {
  font-size: 1.25rem;
  font-weight: 600;
  color: #0f172a;
}

.budget-slider {
  width: 100%;
  accent-color: #3b82f6;
}

.slider-scale {
  display: flex;
  justify-content: space-between;
  font-size: 0.813rem;
  color: #64748b;
}

.notice {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
  border-radius: 8px;
  border: 1px solid;
  font-size: 0.875rem;
}

.notice.success {
  background: #f0fdf4;
  border-color: #bbf7d0;
  color: #166534;
}

.notice.danger {
  background: #fef2f2;
  border-color: #fecaca;
  color: #991b1b;
}

.link-button {
  background: none;
  border: none;
  color: inherit;
  text-decoration: underline;
  cursor: pointer;
  font-size: inherit;
}

.card.refreshing {
  opacity: 0.6;
  transition: opacity 0.15s;
}

.place-order {
  padding: 0.5rem 1.25rem;
  background: #0f172a;
  color: white;
  border: none;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
}

.place-order:hover:not(:disabled) {
  background: #1e293b;
}

.place-order:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.hint {
  margin: 0 0 0.75rem;
  font-size: 0.875rem;
}

.danger-text {
  color: #dc2626;
}

.empty {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}

.restock-table {
  width: 100%;
}

.num {
  text-align: right;
  white-space: nowrap;
}

.col-check {
  width: 40px;
}

.col-qty {
  width: 110px;
}

.qty-input {
  width: 80px;
  padding: 0.25rem 0.5rem;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  text-align: right;
  color: #0f172a;
}

.deselected td {
  color: #94a3b8;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
}
</style>
