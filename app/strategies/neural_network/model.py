import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
import tensorflow as tf
import numpy as np
from sklearn.preprocessing import MinMaxScaler

class NeuralPredictor:
    def __init__(
        self,
        sequence_length: int = 20,
        features: int = 5,
        prediction_steps: int = 3
    ):
        self.sequence_length = sequence_length
        self.features = features
        self.prediction_steps = prediction_steps
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.model = self.build_model()
        
    def build_model(self) -> tf.keras.Model:
        """Создает LSTM модель для прогнозирования с правильным указанием input_shape"""
            
        model = tf.keras.Sequential()
        
        # Добавляем Input слой вместо указания input_shape в LSTM
        model.add(tf.keras.layers.Input(
            shape=(self.sequence_length, self.features),
            name="input_layer"
        ))
        
        model.add(tf.keras.layers.LSTM(
            128, 
            return_sequences=True,
            name="lstm_1"
        ))
        model.add(tf.keras.layers.Dropout(0.3))
        model.add(tf.keras.layers.LSTM(
            64, 
            return_sequences=False,
            name="lstm_2"
        ))
        model.add(tf.keras.layers.Dropout(0.3))
        model.add(tf.keras.layers.Dense(32, activation='relu', name="dense_1"))
        model.add(tf.keras.layers.Dense(self.prediction_steps, name="output"))
        
        model.compile(optimizer='adam', loss='mse')
        return model
    
    # Остальные методы без изменений
    def prepare_data(self, candles):
        """Подготавливает данные для обучения/прогноза"""
        data = np.array([
            [c['open'], c['high'], c['low'], c['close'], c['volume']] 
            for c in candles
        ])
        return self.scaler.fit_transform(data)
    
    def train(self, data, epochs=50, batch_size=32):
        """Обучает модель на исторических данных"""
        if len(data) < self.sequence_length + self.prediction_steps:
            raise ValueError("Недостаточно данных для обучения")
            
        X, y = [], []
        for i in range(len(data) - self.sequence_length - self.prediction_steps):
            X.append(data[i:i+self.sequence_length])
            y.append(data[i+self.sequence_length:i+self.sequence_length+self.prediction_steps, 3])
        
        X = np.array(X)
        y = np.array(y)
        
        return self.model.fit(X, y, epochs=epochs, batch_size=batch_size, validation_split=0.1)
    
    def predict(self, data):
        """Делает прогноз на основе последних данных"""
        # Проверка входных данных
        if len(data) < self.sequence_length:
            raise ValueError(f"Недостаточно данных. Требуется: {self.sequence_length}, получено: {len(data)}")
        
        # Преобразование данных
        scaled_data = self.scaler.transform(data)
        
        # Подготовка последовательности для прогноза
        sequence = scaled_data[-self.sequence_length:]
        sequence = np.array([sequence])  # Добавляем размерность батча
        
        # Получение прогноза
        prediction = self.model.predict(sequence)
        
        # Создаем временный массив с правильной структурой для обратного преобразования
        # Форма: (количество прогнозов, количество признаков)
        dummy = np.zeros((prediction.shape[1], self.features))
        
        # Помещаем прогнозы в столбец закрытия (индекс 3)
        dummy[:, 3] = prediction[0]
        
        # Применяем обратное преобразование
        unscaled = self.scaler.inverse_transform(dummy)
        
        # Возвращаем только прогнозы закрытия
        return unscaled[:, 3]
    
    def save(self, path):
        """Сохраняет модель в современном формате"""
        self.model.save(f"{path}.keras")
        # Сохраняем параметры scaler отдельно
        np.savez(f"{path}_scaler.npz", scale=self.scaler.scale_, min=self.scaler.min_)
    
    def load(self, path):
        # Убедимся, что путь не содержит лишних расширений
        base_path = path.replace('.keras', '')
        
        model_path = f"{base_path}.keras"
        scaler_path = f"{base_path}_scaler.npz"
        
        if not os.path.exists(model_path) or not os.path.exists(scaler_path):
            available_files = os.listdir(os.path.dirname(base_path))
            raise FileNotFoundError(
                f"Модель или скалер не найдены:\n"
                f"• {model_path}\n"
                f"• {scaler_path}\n"
                f"Доступные файлы: {available_files}"
            )
        
        self.model = tf.keras.models.load_model(model_path)
        scaler_data = np.load(scaler_path)
        self.scaler.scale_ = scaler_data['scale']
        self.scaler.min_ = scaler_data['min']