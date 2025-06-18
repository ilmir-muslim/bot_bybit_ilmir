<template>
  <div class="p-6 max-w-md mx-auto bg-white rounded-xl shadow-md space-y-4">
    <h1 class="text-xl font-bold text-center">Управление ботом</h1>
    <p class="text-center text-gray-600">Статус: 
      <span :class="statusClass">{{ status }}</span>
    </p>

    <div class="flex justify-around">
      <button
        class="bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-4 rounded"
        @click="startBot"
      >
        ▶️ Старт
      </button>
      <button
        class="bg-red-500 hover:bg-red-600 text-white font-bold py-2 px-4 rounded"
        @click="stopBot"
      >
        ⏹ Стоп
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const status = ref('unknown')

const fetchStatus = async () => {
  try {
    const res = await axios.get('/api/bot/status')
    status.value = res.data.status
  } catch (err) {
    status.value = 'error'
  }
}

const startBot = async () => {
  await axios.post('/api/bot/start')
  await fetchStatus()
}

const stopBot = async () => {
  await axios.post('/api/bot/stop')
  await fetchStatus()
}

const statusClass = computed(() =>
  status.value === 'running'
    ? 'text-green-600 font-semibold'
    : status.value === 'stopped'
    ? 'text-red-600 font-semibold'
    : 'text-yellow-600 font-semibold'
)

onMounted(() => {
  fetchStatus()
  setInterval(fetchStatus, 5000)
})
</script>
