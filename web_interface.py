from flask import Flask, render_template, request, jsonify, redirect, url_for
import json
import os
from config import CHANNELS_CONFIG_FILE

app = Flask(__name__)

def load_channels_config():
    """Загрузка конфигурации каналов"""
    if os.path.exists(CHANNELS_CONFIG_FILE):
        with open(CHANNELS_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'channels': {}}

def save_channels_config(config):
    """Сохранение конфигурации каналов"""
    with open(CHANNELS_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

@app.route('/')
def index():
    """Главная страница интерфейса"""
    config = load_channels_config()
    channels = config.get('channels', {})
    return render_template('index.html', channels=channels)

@app.route('/add_channel', methods=['POST'])
def add_channel():
    """Добавление нового канала"""
    data = request.json
    channel_id = data.get('channel_id')
    sources = data.get('sources', [])
    keywords = data.get('keywords', [])
    style = data.get('style', 'neutral')
    
    if not channel_id:
        return jsonify({'success': False, 'message': 'ID канала обязателен'}), 400
    
    config = load_channels_config()
    config['channels'][channel_id] = {
        'sources': sources,
        'keywords': keywords,
        'style': style
    }
    
    save_channels_config(config)
    return jsonify({'success': True, 'message': f'Канал {channel_id} добавлен'})

@app.route('/remove_channel/<channel_id>', methods=['DELETE'])
def remove_channel(channel_id):
    """Удаление канала"""
    config = load_channels_config()
    
    if channel_id in config['channels']:
        del config['channels'][channel_id]
        save_channels_config(config)
        return jsonify({'success': True, 'message': f'Канал {channel_id} удален'})
    else:
        return jsonify({'success': False, 'message': 'Канал не найден'}), 404

@app.route('/update_channel/<channel_id>', methods=['PUT'])
def update_channel(channel_id):
    """Обновление настроек канала"""
    data = request.json
    sources = data.get('sources', [])
    keywords = data.get('keywords', [])
    style = data.get('style', 'neutral')
    
    config = load_channels_config()
    
    if channel_id in config['channels']:
        config['channels'][channel_id] = {
            'sources': sources,
            'keywords': keywords,
            'style': style
        }
        save_channels_config(config)
        return jsonify({'success': True, 'message': f'Настройки канала {channel_id} обновлены'})
    else:
        return jsonify({'success': False, 'message': 'Канал не найден'}), 404

@app.route('/get_channel/<channel_id>')
def get_channel(channel_id):
    """Получение информации о канале"""
    config = load_channels_config()
    
    if channel_id in config['channels']:
        return jsonify({'success': True, 'channel': config['channels'][channel_id]})
    else:
        return jsonify({'success': False, 'message': 'Канал не найден'}), 404

@app.route('/logs')
def logs():
    """Страница просмотра логов"""
    # Читаем последние строки из лог-файла
    log_lines = []
    try:
        with open('bot.log', 'r', encoding='utf-8') as f:
            lines = f.readlines()
            # Берем последние 100 строк
            log_lines = lines[-100:]
    except FileNotFoundError:
        log_lines = ["Лог-файл пока пуст"]
    
    return render_template('logs.html', logs=log_lines)

if __name__ == '__main__':
    # Создаем директорию templates, если она не существует
    os.makedirs('templates', exist_ok=True)
    
    # Создаем базовые HTML-шаблоны
    index_template = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Управление ботом</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #007bff;
            padding-bottom: 10px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        input, select, textarea {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
        }
        button {
            background-color: #007bff;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        button:hover {
            background-color: #0056b3;
        }
        .btn-danger {
            background-color: #dc3545;
        }
        .btn-danger:hover {
            background-color: #c82333;
        }
        .btn-warning {
            background-color: #ffc107;
            color: black;
        }
        .btn-warning:hover {
            background-color: #e0a800;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f8f9fa;
        }
        .actions {
            display: flex;
            gap: 5px;
        }
        .alert {
            padding: 10px;
            margin: 10px 0;
            border-radius: 4px;
        }
        .alert-success {
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .alert-error {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Управление ботом публикации статей</h1>
        
        <div id="message"></div>
        
        <h2>Добавить новый канал</h2>
        <form id="addChannelForm">
            <div class="form-group">
                <label for="channelId">ID канала:</label>
                <input type="text" id="channelId" name="channelId" required placeholder="-1001234567890">
            </div>
            
            <div class="form-group">
                <label for="sources">Источники (по одному URL на строку):</label>
                <textarea id="sources" name="sources" rows="3" placeholder="https://example.com&#10;https://another-source.com"></textarea>
            </div>
            
            <div class="form-group">
                <label for="keywords">Ключевые слова (через запятую):</label>
                <input type="text" id="keywords" name="keywords" placeholder="python, programming, development">
            </div>
            
            <div class="form-group">
                <label for="style">Стиль подачи материала:</label>
                <select id="style" name="style">
                    <option value="neutral">Нейтральный</option>
                    <option value="informal">Неформальный</option>
                    <option value="formal">Формальный</option>
                    <option value="promotional">Продвигающий</option>
                </select>
            </div>
            
            <button type="submit">Добавить канал</button>
        </form>
        
        <h2>Список каналов</h2>
        {% if channels %}
        <table>
            <thead>
                <tr>
                    <th>ID канала</th>
                    <th>Источники</th>
                    <th>Ключевые слова</th>
                    <th>Стиль</th>
                    <th>Действия</th>
                </tr>
            </thead>
            <tbody>
                {% for channel_id, settings in channels.items() %}
                <tr id="row-{{ channel_id }}">
                    <td>{{ channel_id }}</td>
                    <td>{{ settings.sources | join(', ') }}</td>
                    <td>{{ settings.keywords | join(', ') }}</td>
                    <td>{{ settings.style }}</td>
                    <td class="actions">
                        <button class="btn-warning" onclick="editChannel('{{ channel_id }}')">Изменить</button>
                        <button class="btn-danger" onclick="deleteChannel('{{ channel_id }}')">Удалить</button>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p>Пока нет добавленных каналов.</p>
        {% endif %}
        
        <h2>Дополнительные действия</h2>
        <a href="{{ url_for('logs') }}"><button class="btn-warning">Просмотреть логи</button></a>
    </div>
    
    <script>
        // Функция для отображения сообщений
        function showMessage(message, isSuccess) {
            const messageDiv = document.getElementById('message');
            messageDiv.innerHTML = `<div class="alert alert-${isSuccess ? 'success' : 'error'}">${message}</div>`;
            
            // Автоматически скрываем сообщение через 5 секунд
            setTimeout(() => {
                messageDiv.innerHTML = '';
            }, 5000);
        }
        
        // Обработка формы добавления канала
        document.getElementById('addChannelForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const channelId = document.getElementById('channelId').value;
            const sourcesText = document.getElementById('sources').value;
            const keywordsText = document.getElementById('keywords').value;
            const style = document.getElementById('style').value;
            
            // Преобразуем текст в массивы
            const sources = sourcesText.split('\\n').map(s => s.trim()).filter(s => s);
            const keywords = keywordsText.split(',').map(k => k.trim()).filter(k => k);
            
            try {
                const response = await fetch('/add_channel', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        channel_id: channelId,
                        sources: sources,
                        keywords: keywords,
                        style: style
                    })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    showMessage(result.message, true);
                    // Обновляем страницу для отображения нового канала
                    location.reload();
                } else {
                    showMessage(result.message, false);
                }
            } catch (error) {
                showMessage('Ошибка при добавлении канала: ' + error.message, false);
            }
        });
        
        // Функция удаления канала
        async function deleteChannel(channelId) {
            if (!confirm(`Вы уверены, что хотите удалить канал ${channelId}?`)) {
                return;
            }
            
            try {
                const response = await fetch(`/remove_channel/${channelId}`, {
                    method: 'DELETE'
                });
                
                const result = await response.json();
                
                if (result.success) {
                    showMessage(result.message, true);
                    // Удаляем строку из таблицы
                    document.getElementById(`row-${channelId}`).remove();
                } else {
                    showMessage(result.message, false);
                }
            } catch (error) {
                showMessage('Ошибка при удалении канала: ' + error.message, false);
            }
        }
        
        // Функция редактирования канала (пока просто показывает алерт)
        function editChannel(channelId) {
            alert('Редактирование канала ' + channelId + ' будет реализовано в следующей версии');
        }
    </script>
</body>
</html>'''

    logs_template = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Логи бота</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #007bff;
            padding-bottom: 10px;
        }
        .log-container {
            background-color: #f8f9fa;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 15px;
            height: 600px;
            overflow-y: scroll;
            font-family: monospace;
            white-space: pre-wrap;
        }
        .back-link {
            display: inline-block;
            margin-top: 15px;
            color: #007bff;
            text-decoration: none;
        }
        .back-link:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Логи бота</h1>
        
        <div class="log-container">
            {% for log in logs %}
                {{ log }}
            {% endfor %}
        </div>
        
        <a href="{{ url_for('index') }}" class="back-link">← Вернуться к управлению</a>
    </div>
</body>
</html>'''
    
    # Записываем шаблоны в файлы
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(index_template)
    
    with open('templates/logs.html', 'w', encoding='utf-8') as f:
        f.write(logs_template)
    
    app.run(debug=True, host='0.0.0.0', port=5000)