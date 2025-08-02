import React, { useState, useEffect } from 'react';
import './App.css';

function App() {
  const [config, setConfig] = useState({
    api_key: '',
    secret_key: '',
    symbol: 'BTCUSDT',
    buy_quantity: 0.001,
    sell_quantity: 0.001,
    max_price_deviation: 0.05
  });
  
  const [botStatus, setBotStatus] = useState({
    running: false,
    message: ''
  });
  
  const [logs, setLogs] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  const backendUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

  // Fetch bot status periodically
  useEffect(() => {
    const interval = setInterval(fetchBotStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  const fetchBotStatus = async () => {
    try {
      const response = await fetch(`${backendUrl}/api/bot-status`);
      const status = await response.json();
      setBotStatus(status);
    } catch (error) {
      console.error('Error fetching bot status:', error);
    }
  };

  const addLog = (message, type = 'info') => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs(prev => [...prev.slice(-99), { timestamp, message, type }]);
  };

  const handleInputChange = (e) => {
    const { name, value, type } = e.target;
    setConfig(prev => ({
      ...prev,
      [name]: type === 'number' ? parseFloat(value) : value
    }));
  };

  const startBot = async () => {
    if (!config.api_key || !config.secret_key) {
      addLog('Пожалуйста, введите API ключи', 'error');
      return;
    }

    setIsLoading(true);
    try {
      const response = await fetch(`${backendUrl}/api/start-bot`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(config)
      });

      const result = await response.json();
      
      if (response.ok) {
        addLog(`Бот запущен для пары ${config.symbol}`, 'success');
        await fetchBotStatus();
      } else {
        addLog(`Ошибка запуска: ${result.detail}`, 'error');
      }
    } catch (error) {
      addLog(`Ошибка соединения: ${error.message}`, 'error');
    } finally {
      setIsLoading(false);
    }
  };

  const stopBot = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`${backendUrl}/api/stop-bot`, {
        method: 'POST'
      });

      const result = await response.json();
      
      if (response.ok) {
        addLog('Бот остановлен', 'success');
        await fetchBotStatus();
      } else {
        addLog(`Ошибка остановки: ${result.detail}`, 'error');
      }
    } catch (error) {
      addLog(`Ошибка соединения: ${error.message}`, 'error');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="App">
      <div className="container">
        <header className="header">
          <h1>🤖 MEXC Trading Bot</h1>
          <p>Автоматический торговый бот для биржи MEXC</p>
        </header>

        {/* Configuration Section */}
        <div className="config-section">
          <h2>⚙️ Настройки</h2>
          
          <div className="config-grid">
            <div className="config-group">
              <label>API Key:</label>
              <input
                type="password"
                name="api_key"
                value={config.api_key}
                onChange={handleInputChange}
                placeholder="Введите API ключ MEXC"
                className="input-field"
              />
            </div>

            <div className="config-group">
              <label>Secret Key:</label>
              <input
                type="password"
                name="secret_key"
                value={config.secret_key}
                onChange={handleInputChange}
                placeholder="Введите Secret ключ MEXC"
                className="input-field"
              />
            </div>

            <div className="config-group">
              <label>Валютная пара:</label>
              <input
                type="text"
                name="symbol"
                value={config.symbol}
                onChange={handleInputChange}
                placeholder="BTCUSDT"
                className="input-field"
              />
            </div>

            <div className="config-group">
              <label>Количество на покупку:</label>
              <input
                type="number"
                name="buy_quantity"
                value={config.buy_quantity}
                onChange={handleInputChange}
                step="0.001"
                min="0.001"
                className="input-field"
              />
            </div>

            <div className="config-group">
              <label>Количество на продажу:</label>
              <input
                type="number"
                name="sell_quantity"
                value={config.sell_quantity}
                onChange={handleInputChange}
                step="0.001"
                min="0.001"
                className="input-field"
              />
            </div>

            <div className="config-group">
              <label>Макс. отклонение цены (%):</label>
              <input
                type="number"
                name="max_price_deviation"
                value={config.max_price_deviation}
                onChange={handleInputChange}
                step="0.01"
                min="0.01"
                max="0.5"
                className="input-field"
              />
            </div>
          </div>

          <div className="button-group">
            <button 
              onClick={startBot} 
              disabled={isLoading || botStatus.running}
              className="btn btn-start"
            >
              {isLoading ? '⏳ Запуск...' : '▶️ Запустить бота'}
            </button>
            
            <button 
              onClick={stopBot} 
              disabled={isLoading || !botStatus.running}
              className="btn btn-stop"
            >
              {isLoading ? '⏳ Остановка...' : '⏹️ Остановить бота'}
            </button>
          </div>
        </div>

        {/* Status Section */}
        <div className="status-section">
          <h2>📊 Статус бота</h2>
          
          <div className="status-grid">
            <div className="status-item">
              <span className="status-label">Состояние:</span>
              <span className={`status-value ${botStatus.running ? 'running' : 'stopped'}`}>
                {botStatus.running ? '🟢 Работает' : '🔴 Остановлен'}
              </span>
            </div>

            {botStatus.symbol && (
              <div className="status-item">
                <span className="status-label">Пара:</span>
                <span className="status-value">{botStatus.symbol}</span>
              </div>
            )}

            {botStatus.best_bid && (
              <div className="status-item">
                <span className="status-label">Лучшая покупка:</span>
                <span className="status-value">{botStatus.best_bid}</span>
              </div>
            )}

            {botStatus.best_ask && (
              <div className="status-item">
                <span className="status-label">Лучшая продажа:</span>
                <span className="status-value">{botStatus.best_ask}</span>
              </div>
            )}

            {botStatus.spread && (
              <div className="status-item">
                <span className="status-label">Спред:</span>
                <span className="status-value">{botStatus.spread}</span>
              </div>
            )}

            {botStatus.initial_price && (
              <div className="status-item">
                <span className="status-label">Начальная цена:</span>
                <span className="status-value">{botStatus.initial_price}</span>
              </div>
            )}
          </div>

          {/* Active Orders */}
          {(botStatus.current_buy_order || botStatus.current_sell_order) && (
            <div className="orders-section">
              <h3>Активные ордера</h3>
              
              {botStatus.current_buy_order && (
                <div className="order-item buy-order">
                  <strong>🟢 Покупка:</strong>
                  <span>Цена: {botStatus.current_buy_order.price}</span>
                  <span>ID: {botStatus.current_buy_order.orderId}</span>
                </div>
              )}

              {botStatus.current_sell_order && (
                <div className="order-item sell-order">
                  <strong>🔴 Продажа:</strong>
                  <span>Цена: {botStatus.current_sell_order.price}</span>
                  <span>ID: {botStatus.current_sell_order.orderId}</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Logs Section */}
        <div className="logs-section">
          <h2>📝 Журнал событий</h2>
          <div className="logs-container">
            {logs.length === 0 ? (
              <p className="no-logs">Журнал пуст</p>
            ) : (
              logs.map((log, index) => (
                <div key={index} className={`log-item ${log.type}`}>
                  <span className="log-time">{log.timestamp}</span>
                  <span className="log-message">{log.message}</span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Help Section */}
        <div className="help-section">
          <h2>ℹ️ Инструкция</h2>
          <div className="help-content">
            <ol>
              <li>Получите API ключи в личном кабинете MEXC (разрешения: торговля)</li>
              <li>Введите API ключи и настройки торговли</li>
              <li>Выберите валютную пару в формате XXXUSDT</li>
              <li>Установите размеры ордеров и максимальное отклонение цены</li>
              <li>Нажмите "Запустить бота" для начала работы</li>
            </ol>
            
            <div className="warning">
              <strong>⚠️ Внимание:</strong> Торговля криптовалютами связана с высокими рисками. 
              Используйте только те средства, потерю которых можете себе позволить.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;