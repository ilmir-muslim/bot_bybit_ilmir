<template>
  <div>
    <h2 class="text-xl font-bold mb-4">История сделок</h2>
    <ul>
      <li v-for="item in trades" :key="item.id">
        {{ item.symbol }} — {{ item.side }} по {{ item.price }} USDT
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const trades = ref([])

onMounted(async () => {
  const res = await fetch('http://localhost:8000/api/trade-log')
  trades.value = await res.json()
})
</script>