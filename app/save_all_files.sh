#!/bin/bash

# Точка запуска — остаётся в app/
output_file="output.txt"
> "$output_file"  # очистка/создание выходного файла

# Пути, которые нужно исключить (по вхождению подстроки)
EXCLUDED_PATTERNS=(
  "/__pycache__/"
  "./save_all_files.sh"
  "./output.txt"
  "./../api/routes/bot_control.py"
  "./../api/routes/trade_log.py"
)

# Проверка: путь содержит исключённый фрагмент?
is_excluded() {
  local path="$1"
  for pattern in "${EXCLUDED_PATTERNS[@]}"; do
    if [[ "$path" == *"$pattern"* ]]; then
      return 0
    fi
  done
  return 1
}

# Сохраняем содержимое всех файлов в текущей директории и ниже
find . -type f | while read file; do
  if ! is_excluded "$file"; then
    echo "===== $file =====" >> "$output_file"
    cat "$file" >> "$output_file"
    echo -e "\n" >> "$output_file"
  fi
done

# Добавляем содержимое run_bot.py из корня проекта
echo "===== ../run_bot.py (добавлено отдельно) =====" >> "$output_file"
cat ../run_bot.py >> "$output_file"
echo -e "\n" >> "$output_file"

# Добавляем вывод tree из корня проекта
echo "===== Структура проекта (tree из ../) =====" >> "$output_file"
tree ../ -I "venv|__pycache__|project_structure.txt|node_modules" >> "$output_file"

xclip -selection clipboard < "$output_file"
echo "📋 Содержимое скопировано в буфер (xclip)"

echo "✅ Всё сохранено в '$output_file'"
