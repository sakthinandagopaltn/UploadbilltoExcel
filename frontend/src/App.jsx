import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchExpenses, processBill } from './api'

const CATEGORY_LABELS = {
  restaurant: 'Restaurant',
  shop: 'Shop',
  medicine: 'Medicine',
  other: 'Other',
}

const CATEGORY_ICONS = {
  restaurant: '🍽️',
  shop: '🛒',
  medicine: '💊',
  other: '📄',
}

function Hero() {
  return (
    <header className="hero">
      <h1>🧾 Family Expense Tracker</h1>
      <p>Upload a bill photo — we read the amount and save it to your Excel file.</p>
    </header>
  )
}

function ResultCard({ result }) {
  const icon = CATEGORY_ICONS[result.category] || '📄'
  const categoryLabel = CATEGORY_LABELS[result.category] || result.category

  return (
    <div className="success-card">
      <div className="success-title">✅ Expense saved to Excel</div>
      <div className="detail-grid">
        <div className="detail-item">
          <div className="detail-label">Amount</div>
          <div className="detail-value amount">${result.amount.toFixed(2)}</div>
        </div>
        <div className="detail-item">
          <div className="detail-label">Date recorded</div>
          <div className="detail-value">{result.date}</div>
        </div>
        <div className="detail-item">
          <div className="detail-label">Category</div>
          <div className="detail-value">
            {icon} {categoryLabel}
          </div>
        </div>
        <div className="detail-item">
          <div className="detail-label">Description</div>
          <div className="detail-value">{result.description}</div>
        </div>
      </div>
      <div className="excel-banner">
        📊 Uploaded to <strong>{result.excel_filename}</strong>
      </div>
    </div>
  )
}

function RecentExpenses({ expenses }) {
  if (!expenses.length) {
    return <p className="muted">No expenses recorded yet. Your first bill will appear here.</p>
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Amount</th>
            <th>Category</th>
            <th>Description</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          {expenses.map((row, index) => (
            <tr key={`${row.date}-${index}`}>
              <td>{row.date}</td>
              <td>${Number(row.amount).toFixed(2)}</td>
              <td>{CATEGORY_LABELS[row.category] || row.category}</td>
              <td>{row.description}</td>
              <td>{row.source_image}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function App() {
  const fileInputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [dragActive, setDragActive] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [expenses, setExpenses] = useState([])

  const loadExpenses = useCallback(async () => {
    try {
      const data = await fetchExpenses()
      setExpenses(data.expenses || [])
    } catch {
      setExpenses([])
    }
  }, [])

  useEffect(() => {
    loadExpenses()
  }, [loadExpenses])

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null)
      return undefined
    }
    const url = URL.createObjectURL(file)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  function handleFileSelected(selectedFile) {
    if (!selectedFile) return
    setFile(selectedFile)
    setError('')
    setResult(null)
  }

  function onDrop(event) {
    event.preventDefault()
    setDragActive(false)
    const dropped = event.dataTransfer.files?.[0]
    if (dropped) handleFileSelected(dropped)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!file) {
      setError('Please upload a bill image first.')
      return
    }

    setLoading(true)
    setError('')
    try {
      const data = await processBill(file)
      setResult(data)
      await loadExpenses()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <div className="container">
        <Hero />

        <div className="grid">
          <section className="panel">
            <h2>Upload your bill</h2>

            <form onSubmit={handleSubmit}>
              <div
                className={`dropzone ${dragActive ? 'active' : ''}`}
                onDragEnter={(e) => {
                  e.preventDefault()
                  setDragActive(true)
                }}
                onDragOver={(e) => e.preventDefault()}
                onDragLeave={() => setDragActive(false)}
                onDrop={onDrop}
                onClick={() => fileInputRef.current?.click()}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click()
                }}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  hidden
                  onChange={(e) => handleFileSelected(e.target.files?.[0])}
                />
                <div className="dropzone-icon">📤</div>
                <p className="dropzone-title">
                  {file ? file.name : 'Drag and drop your bill here'}
                </p>
                <p className="dropzone-hint">or click to browse (JPG, PNG, WEBP)</p>
              </div>

              {previewUrl && (
                <div className="preview-box">
                  <img src={previewUrl} alt="Bill preview" />
                </div>
              )}

              {error && <div className={`error-box${error.includes('already been uploaded') ? ' duplicate' : ''}`}>{error}</div>}

              <button type="submit" className="primary-btn" disabled={!file || loading}>
                {loading ? 'Reading your bill…' : 'Scan bill & save to Excel'}
              </button>
            </form>
          </section>

          <section className="panel">
            <h2>Bill details</h2>
            {result ? (
              <ResultCard result={result} />
            ) : (
              <div className="info-box">
                Upload a bill and click <strong>Scan bill & save to Excel</strong> to see the
                detected amount, date, and confirmation here.
              </div>
            )}
          </section>
        </div>

        <section className="panel recent">
          <h2>Recent expenses</h2>
          <RecentExpenses expenses={expenses} />
        </section>
      </div>
    </div>
  )
}
