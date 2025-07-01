import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import numpy as np
from app.strategies.neural_network.model import NeuralPredictor


# Тестовые данные
data = np.random.rand(100, 5)  # 100 свечей, 5 признаков

# Создаем и тестируем модель
predictor = NeuralPredictor(sequence_length=60, features=5, prediction_steps=3)
predictor.scaler.fit(data)  # Фиктивное обучение для теста

# Делаем прогноз
test_data = np.random.rand(60, 5)  # 60 последних свечей
predictions = predictor.predict(test_data)

print(f"Прогнозы: {predictions}")
print(f"Размер прогнозов: {predictions.shape}")