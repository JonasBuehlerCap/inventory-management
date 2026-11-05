<template>
  <div class="reports">
    <div class="page-header">
      <h2>{{ t('reports.title') }}</h2>
      <p>{{ t('reports.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('reports.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="!hasData" class="loading">{{ t('reports.noData') }}</div>
    <div v-else>
      <!-- Quarterly Performance -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('reports.quarterly.title') }}</h3>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('reports.quarterly.quarter') }}</th>
                <th>{{ t('reports.quarterly.totalOrders') }}</th>
                <th>{{ t('reports.quarterly.totalRevenue') }}</th>
                <th>{{ t('reports.quarterly.avgOrderValue') }}</th>
                <th>{{ t('reports.quarterly.fulfillmentRate') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="q in quarterlyData" :key="q.quarter">
                <td>
                  <strong>{{ q.quarter }}</strong>
                </td>
                <td>{{ q.total_orders }}</td>
                <td>{{ formatCurrency(q.total_revenue, currentCurrency) }}</td>
                <td>{{ formatCurrencyWithDecimals(q.avg_order_value, currentCurrency, 2) }}</td>
                <td>
                  <span :class="['badge', getFulfillmentClass(q.fulfillment_rate)]">
                    {{ formatPercent(q.fulfillment_rate) }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Monthly Trends Chart -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('reports.trend.title') }}</h3>
        </div>
        <div class="chart-container">
          <div class="bar-chart" role="img" :aria-label="t('reports.trend.chartLabel')">
            <div v-for="month in monthRows" :key="month.month" class="bar-wrapper">
              <div class="bar-container">
                <div
                  class="bar"
                  :style="{ height: month.barHeight + 'px' }"
                  :title="formatCurrency(month.revenue, currentCurrency)"
                ></div>
              </div>
              <div class="bar-label">{{ month.label }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Month-over-Month Comparison -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('reports.mom.title') }}</h3>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('reports.mom.month') }}</th>
                <th>{{ t('reports.mom.orders') }}</th>
                <th>{{ t('reports.mom.revenue') }}</th>
                <th>{{ t('reports.mom.change') }}</th>
                <th>{{ t('reports.mom.growthRate') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="month in monthRows" :key="month.month">
                <td>
                  <strong>{{ month.label }}</strong>
                </td>
                <td>{{ month.order_count }}</td>
                <td>{{ formatCurrency(month.revenue, currentCurrency) }}</td>
                <td>
                  <span v-if="month.changeText" :class="month.changeClass">{{ month.changeText }}</span>
                  <span v-else>-</span>
                </td>
                <td>
                  <span v-if="month.growthText" :class="month.changeClass">{{ month.growthText }}</span>
                  <span v-else>-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Summary Stats -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.stats.totalRevenue') }}</div>
          <div class="stat-value">{{ formatCurrency(totalRevenue, currentCurrency) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.stats.avgMonthlyRevenue') }}</div>
          <div class="stat-value">{{ formatCurrency(avgMonthlyRevenue, currentCurrency) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.stats.totalOrders') }}</div>
          <div class="stat-value">{{ totalOrders.toLocaleString(numberLocale) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.stats.bestQuarter') }}</div>
          <div class="stat-value">{{ bestQuarter || '-' }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'

// Max bar height in px; matches .bar-container height in the styles below
const MAX_BAR_HEIGHT = 200
const MONTH_KEYS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']

export default {
  name: 'Reports',
  setup() {
    const { t, currentCurrency, currentLocale } = useI18n()
    const { selectedPeriod, selectedLocation, selectedCategory, selectedStatus, getCurrentFilters } = useFilters()

    const loading = ref(true)
    const error = ref(null)
    const quarterlyData = ref([])
    const monthlyData = ref([])

    const numberLocale = computed(() => (currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'))

    const loadData = async () => {
      loading.value = true
      error.value = null
      try {
        const filters = getCurrentFilters()
        const [quarterly, monthly] = await Promise.all([
          api.getQuarterlyReports(filters),
          api.getMonthlyTrends(filters)
        ])
        quarterlyData.value = Array.isArray(quarterly) ? quarterly : []
        monthlyData.value = Array.isArray(monthly) ? monthly : []
      } catch (err) {
        error.value = t('reports.loadError', { message: err.message })
        console.error('Failed to load reports:', err)
      } finally {
        loading.value = false
      }
    }

    // Reload whenever any global filter changes
    watch([selectedPeriod, selectedLocation, selectedCategory, selectedStatus], () => {
      loadData()
    })

    onMounted(() => {
      loadData()
    })

    // Derived summary stats; reduce on empty arrays yields 0 so no extra guards needed
    const totalRevenue = computed(() => monthlyData.value.reduce((sum, m) => sum + m.revenue, 0))
    const totalOrders = computed(() => monthlyData.value.reduce((sum, m) => sum + m.order_count, 0))
    const avgMonthlyRevenue = computed(() =>
      monthlyData.value.length > 0 ? totalRevenue.value / monthlyData.value.length : 0
    )
    const maxRevenue = computed(() => Math.max(0, ...monthlyData.value.map((m) => m.revenue)))
    const bestQuarter = computed(() => {
      if (quarterlyData.value.length === 0) return ''
      const best = quarterlyData.value.reduce((a, b) => (b.total_revenue > a.total_revenue ? b : a))
      return best.total_revenue > 0 ? best.quarter : ''
    })

    const hasData = computed(() => quarterlyData.value.length > 0 || monthlyData.value.length > 0)

    // Convert "YYYY-MM" to e.g. "Jan 2025" (en) or "2025年1月" (ja); falls back to the raw string if malformed
    const formatMonth = (monthStr) => {
      const [year, month] = String(monthStr).split('-')
      const key = MONTH_KEYS[parseInt(month, 10) - 1]
      if (!year || !key) return String(monthStr)
      const label = t(`months.${key}`)
      return currentLocale.value === 'ja' ? `${year}年${label}` : `${label} ${year}`
    }

    const formatPercent = (value) =>
      `${Number(value).toLocaleString(numberLocale.value, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`

    const getFulfillmentClass = (rate) => {
      if (rate >= 90) return 'success'
      if (rate >= 75) return 'warning'
      return 'danger'
    }

    // Per-month display rows: label, bar height and change vs the previous month,
    // computed once instead of per-bar / per-cell rescans in the template
    const monthRows = computed(() =>
      monthlyData.value.map((m, i) => {
        const prev = i > 0 ? monthlyData.value[i - 1] : null
        const row = {
          ...m,
          label: formatMonth(m.month),
          barHeight: maxRevenue.value > 0 ? (m.revenue / maxRevenue.value) * MAX_BAR_HEIGHT : 0,
          changeText: '',
          growthText: '',
          changeClass: ''
        }
        if (prev) {
          const change = m.revenue - prev.revenue
          const sign = change > 0 ? '+' : change < 0 ? '-' : ''
          row.changeText = sign + formatCurrency(Math.abs(change), currentCurrency.value)
          // Growth is undefined when the previous month has zero revenue
          if (prev.revenue === 0) {
            row.growthText = 'N/A'
          } else {
            const rate = (change / prev.revenue) * 100
            row.growthText = (rate > 0 ? '+' : '') + formatPercent(rate)
          }
          row.changeClass = change > 0 ? 'positive-change' : change < 0 ? 'negative-change' : ''
        }
        return row
      })
    )

    return {
      t,
      currentCurrency,
      numberLocale,
      loading,
      error,
      quarterlyData,
      monthRows,
      hasData,
      totalRevenue,
      avgMonthlyRevenue,
      totalOrders,
      bestQuarter,
      formatCurrency,
      formatCurrencyWithDecimals,
      formatPercent,
      getFulfillmentClass
    }
  }
}
</script>

<style scoped>
/* Shared card/stat/badge/loading/error/table styles come from App.vue; only Reports-specific styles here */
.chart-container {
  padding: 2rem 1rem;
  min-height: 300px;
}

.bar-chart {
  display: flex;
  align-items: flex-end;
  justify-content: space-around;
  height: 250px;
  gap: 0.5rem;
}

.bar-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  max-width: 80px;
}

.bar-container {
  height: 200px;
  display: flex;
  align-items: flex-end;
  width: 100%;
}

.bar {
  width: 100%;
  background: linear-gradient(to top, #3b82f6, #60a5fa);
  border-radius: 4px 4px 0 0;
  transition: all 0.3s;
  cursor: pointer;
}

.bar:hover {
  background: linear-gradient(to top, #2563eb, #3b82f6);
}

.bar-label {
  font-size: 0.75rem;
  color: #64748b;
  text-align: center;
  transform: rotate(-45deg);
  white-space: nowrap;
  margin-top: 1.5rem;
}

.positive-change {
  color: #16a34a;
  font-weight: 600;
}

.negative-change {
  color: #dc2626;
  font-weight: 600;
}
</style>
