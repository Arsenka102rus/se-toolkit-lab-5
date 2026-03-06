import { useState, useEffect, useReducer, FormEvent } from 'react'
import Dashboard from './Dashboard'
import './App.css'

const STORAGE_KEY = 'api_key'

interface Item {
  id: number
  type: string
  title: string
  created_at: string
}

type FetchState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; items: Item[] }
  | { status: 'error'; message: string }

type FetchAction =
  | { type: 'fetch_start' }
  | { type: 'fetch_success'; data: Item[] }
  | { type: 'fetch_error'; message: string }

function fetchReducer(_state: FetchState, action: FetchAction): FetchState {
  switch (action.type) {
    case 'fetch_start':
      return { status: 'loading' }
    case 'fetch_success':
      return { status: 'success', items: action.data }
    case 'fetch_error':
      return { status: 'error', message: action.message }
  }
}

function App() {
  const [token, setToken] = useState(
    () => localStorage.getItem(STORAGE_KEY) ?? '',
  )
  const [draft, setDraft] = useState('')
  const [currentPage, setCurrentPage] = useState<'items' | 'dashboard'>('items')
  const [fetchState, dispatch] = useReducer(fetchReducer, { status: 'idle' })

  useEffect(() => {
    if (!token) return

    dispatch({ type: 'fetch_start' })

    fetch('/items/', {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((data: Item[]) => dispatch({ type: 'fetch_success', data }))
      .catch((err: Error) =>
        dispatch({ type: 'fetch_error', message: err.message }),
      )
  }, [token])

  function handleConnect(e: FormEvent) {
    e.preventDefault()
    const trimmed = draft.trim()
    if (!trimmed) return
    localStorage.setItem(STORAGE_KEY, trimmed)
    setToken(trimmed)
  }

  function handleDisconnect() {
    localStorage.removeItem(STORAGE_KEY)
    setToken('')
    setDraft('')
  }

  // Если нет токена - показываем форму ввода API ключа
  if (!token) {
    return (
      <form className="token-form" onSubmit={handleConnect}>
        <h1>API Key</h1>
        <p>Enter your API key to connect.</p>
        <input
          type="password"
          placeholder="Token"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button type="submit">Connect</button>
      </form>
    )
  }

  // Если токен есть - показываем основное приложение с навигацией
  return (
    <div>
      {/* Шапка с навигацией и кнопкой Disconnect */}
      <header className="app-header">
        <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
          <h1>Lab Dashboard</h1>
          <nav style={{ display: 'flex', gap: '10px' }}>
            <button
              onClick={() => setCurrentPage('items')}
              style={{
                padding: '5px 15px',
                fontWeight: currentPage === 'items' ? 'bold' : 'normal',
                backgroundColor: currentPage === 'items' ? '#4CAF50' : '#f0f0f0',
                color: currentPage === 'items' ? 'white' : 'black',
                border: '1px solid #ccc',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              Items
            </button>
            <button
              onClick={() => setCurrentPage('dashboard')}
              style={{
                padding: '5px 15px',
                fontWeight: currentPage === 'dashboard' ? 'bold' : 'normal',
                backgroundColor: currentPage === 'dashboard' ? '#4CAF50' : '#f0f0f0',
                color: currentPage === 'dashboard' ? 'white' : 'black',
                border: '1px solid #ccc',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              Dashboard
            </button>
          </nav>
        </div>
        <button className="btn-disconnect" onClick={handleDisconnect}>
          Disconnect
        </button>
      </header>

      {/* Основной контент */}
      <main style={{ padding: '20px' }}>
        {currentPage === 'items' ? (
          // Страница Items (твоя существующая логика)
          <>
            {fetchState.status === 'loading' && <p>Loading...</p>}
            {fetchState.status === 'error' && <p>Error: {fetchState.message}</p>}

            {fetchState.status === 'success' && (
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>ItemType</th>
                    <th>Title</th>
                    <th>Created at</th>
                  </tr>
                </thead>
                <tbody>
                  {fetchState.items.map((item) => (
                    <tr key={item.id}>
                      <td>{item.id}</td>
                      <td>{item.type}</td>
                      <td>{item.title}</td>
                      <td>{item.created_at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        ) : (
          // Страница Dashboard
          <Dashboard />
        )}
      </main>
    </div>
  )
}

export default App  