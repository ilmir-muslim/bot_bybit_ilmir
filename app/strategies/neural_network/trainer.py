import argparse
import os
from .model import NeuralPredictor

def main():
    from app.services.bybit_service import BybitService
    
    parser = argparse.ArgumentParser(description='Обучение торговой нейросети')
    parser.add_argument('--symbol', type=str, default='SOLUSDT', help='Торговый символ')
    parser.add_argument('--interval', type=str, default='5', help='5-минутный интервал')
    parser.add_argument('--epochs', type=int, default=200, help='Количество эпох обучения')
    parser.add_argument('--model_path', type=str, default='models/neural_model.keras', help='Путь для сохранения модели')
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.model_path), exist_ok=True)
    
    bybit = BybitService()
    candles = bybit.get_candles(args.symbol, args.interval, limit=10000)    
    
    # Уменьшили минимальный порог данных
    if not candles or len(candles) < 180:
        print(f"❌ Недостаточно данных для обучения ({len(candles) if candles else 0} < 180)")
        return
    
    # Уменьшили длину последовательности
    predictor = NeuralPredictor(
        sequence_length=30,  # Было 60
        prediction_steps=3
    )
    data = predictor.prepare_data(candles)
    predictor.train(data, epochs=args.epochs)
    
    model_base_path = args.model_path.replace('.keras', '')
    predictor.save(model_base_path)
    print(f"✅ Модель сохранена как: {model_base_path}.keras")
    

if __name__ == "__main__":
    main()