const API_BASE = import.meta.env.VITE_API_URL || ''

export async function fetchExpenses() {
  const response = await fetch(`${API_BASE}/api/expenses`)
  if (!response.ok) {
    throw new Error('Could not load expenses.')
  }
  return response.json()
}

export async function processBill(file) {
  const formData = new FormData()
  formData.append('image', file)

  const response = await fetch(`${API_BASE}/api/process-bill`, {
    method: 'POST',
    body: formData,
  })

  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = data.detail
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((item) => item.msg || item).join(', ')
          : 'Failed to process bill.'
    throw new Error(message)
  }
  return data
}
