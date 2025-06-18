<template>
  <div class="p-4">
    <h2 class="text-xl font-bold mb-4">История сделок</h2>

    <table class="w-full border-collapse border border-gray-300 text-sm">
      <thead class="bg-gray-100">
        <tr>
          <th class="border px-2 py-1">Время</th>
          <th class="border px-2 py-1">Символ</th>
          <th class="border px-2 py-1">Сторона</th>
          <th class="border px-2 py-1">Количество</th>
          <th class="border px-2 py-1">Цена</th>
          <th class="border px-2 py-1">Статус</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="log in logs" :key="log.time">
          <td class="border px-2 py-1">{{ formatDate(log.time) }}</td>
          <td class="border px-2 py-1">{{ log.symbol }}</td>
          <td class="border px-2 py-1">{{ translateSide(log.side) }}</td>
          <td class="border px-2 py-1">{{ log.qty }}</td>
          <td class="border px-2 py-1">{{ log.price }}</td>
          <td class="border px-2 py-1">{{ translateStatus(log.status) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const logs = ref([])

onMounted(async () => {
  const response = await axios.get('/api/trade')
  logs.value = response.data
})

function formatDate(datetime) {
  const date = new Date(datetime)
  return date.toLocaleString('ru-RU')
}

function translateSide(side) {
  return side === 'BUY' ? 'Покупка' : 'Продажа'
}

function translateStatus(status) {
  const map = {
    FILLED: 'Исполнено',
    CANCELLED: 'Отменено',
    PARTIALLY_FILLED: 'Частично исполнено',
    NEW: 'Создано',
    REJECTED: 'Отклонено',
  }
  return map[status] || status
}
</script>
