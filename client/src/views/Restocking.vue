<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <!-- Budget slider -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budget') }}</h3>
          <span class="budget-amount">{{ formatCurrency(budget, currentCurrency) }}</span>
        </div>
        <input
          type="range"
          class="budget-slider"
          min="0"
          max="500000"
          step="5000"
          v-model.number="budget"
        />
        <div class="budget-captions">
          <span>{{ formatCurrency(0, currentCurrency) }}</span>
          <span>{{ formatCurrency(500000, currentCurrency) }}</span>
        </div>
      </div>

      <!-- Summary -->
      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.itemsToOrder') }}</div>
          <div class="stat-value">{{ totalItems }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.totalCost') }}</div>
          <div class="stat-value">{{ formatCurrency(totalCost, currentCurrency) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.remainingBudget') }}</div>
          <div class="stat-value">{{ formatCurrency(remainingBudget, currentCurrency) }}</div>
        </div>
      </div>

      <!-- Success banner -->
      <div v-if="submitSuccess" class="success-banner">
        {{ t('restocking.orderPlaced', { orderNumber: submittedOrderNumber }) }}
      </div>

      <!-- Recommendations -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendations') }}</h3>
          <button
            class="btn-primary"
            :disabled="recommendations.length === 0 || submitting || submitSuccess"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placing') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="recommendations.length === 0" class="empty-state">
          {{ t('restocking.noRecommendations') }}
        </div>

        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.item') }}</th>
                <th>{{ t('restocking.demandGap') }}</th>
                <th>{{ t('restocking.unitCost') }}</th>
                <th>{{ t('restocking.lineCost') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in recommendations" :key="item.sku">
                <td><strong>{{ item.sku }}</strong></td>
                <td>{{ item.name }}</td>
                <td>{{ item.quantity }}</td>
                <td>{{ formatCurrency(item.unit_price, currentCurrency) }}</td>
                <td><strong>{{ formatCurrency(item.cost, currentCurrency) }}</strong></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, watch, computed } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency } from '../utils/currency'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const allForecasts = ref([])
    const budget = ref(50000)
    const submitting = ref(false)
    const submitSuccess = ref(false)
    const submittedOrderNumber = ref(null)

    const loadData = async () => {
      try {
        loading.value = true
        error.value = null  // clear any stale error so a successful reload re-shows the UI
        allForecasts.value = await api.getDemandForecasts()
      } catch (err) {
        error.value = 'Failed to load restocking data: ' + err.message
      } finally {
        loading.value = false
      }
    }

    const recommendations = computed(() => {
      // Each forecast carries its own unit_cost, so items are priced directly.
      // The demand forecast has no warehouse/category dimension, so recommendations
      // are global and not scoped by the FilterBar.
      const candidates = allForecasts.value
        .map(f => ({
          sku: f.item_sku,
          name: f.item_name,
          gap: f.forecasted_demand - f.current_demand,
          unit_cost: f.unit_cost
        }))
        .filter(c => c.gap > 0)
        .sort((a, b) => b.gap - a.gap)

      // Greedy fill: order enough units to close each demand gap, biggest gap first.
      // If an item doesn't fit the remaining budget we skip it and keep going, so a
      // cheaper lower-ranked item can still be included — maximizing budget use.
      const chosen = []
      let remaining = budget.value
      for (const c of candidates) {
        const cost = c.gap * c.unit_cost
        if (cost <= remaining) {
          chosen.push({
            sku: c.sku,
            name: c.name,
            quantity: c.gap,
            unit_price: c.unit_cost,
            cost
          })
          remaining -= cost
        }
      }
      return chosen
    })

    const totalCost = computed(() =>
      recommendations.value.reduce((sum, item) => sum + item.cost, 0)
    )
    const totalItems = computed(() => recommendations.value.length)
    const remainingBudget = computed(() => budget.value - totalCost.value)

    const placeOrder = async () => {
      submitting.value = true
      error.value = null
      submitSuccess.value = false
      try {
        const payload = {
          items: recommendations.value.map(r => ({
            sku: r.sku,
            name: r.name,
            quantity: r.quantity,
            unit_price: r.unit_price
          })),
          budget: budget.value
        }
        const created = await api.createOrder(payload)
        submittedOrderNumber.value = created.order_number
        submitSuccess.value = true
      } catch (err) {
        error.value = 'Failed to place order: ' + err.message
      } finally {
        submitting.value = false
      }
    }

    // Changing the budget produces a new recommendation basket, so any prior
    // "order placed" confirmation is stale and the button should re-enable.
    watch(budget, () => {
      submitSuccess.value = false
    })

    onMounted(loadData)

    return {
      t,
      currentCurrency,
      formatCurrency,
      loading,
      error,
      budget,
      submitting,
      submitSuccess,
      submittedOrderNumber,
      recommendations,
      totalCost,
      totalItems,
      remainingBudget,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-amount {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.budget-slider {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: #e2e8f0;
  outline: none;
  -webkit-appearance: none;
  appearance: none;
  cursor: pointer;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #0f172a;
  cursor: pointer;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.3);
}

.budget-slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #0f172a;
  cursor: pointer;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.3);
}

.budget-captions {
  display: flex;
  justify-content: space-between;
  margin-top: 0.5rem;
  font-size: 0.75rem;
  color: #64748b;
}

.btn-primary {
  background: #0f172a;
  color: #ffffff;
  border: none;
  border-radius: 6px;
  padding: 0.5rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease;
}

.btn-primary:hover:not(:disabled) {
  background: #1e293b;
}

.btn-primary:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.empty-state {
  text-align: center;
  padding: 2.5rem;
  color: #64748b;
  font-size: 0.938rem;
}

.success-banner {
  background: #d1fae5;
  border: 1px solid #6ee7b7;
  color: #065f46;
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 1.25rem;
  font-size: 0.938rem;
  font-weight: 500;
}
</style>
