import { createRouter, createWebHistory } from 'vue-router'
import TradeHistory from '@/components/TradeHistory.vue'

const routes = [
  {
    path: '/',
    name: 'История сделок',
    component: TradeHistory
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
