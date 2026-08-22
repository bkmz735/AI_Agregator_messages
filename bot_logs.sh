#!/bin/bash

echo "Выберите, какие логи вы хотите посмотреть:"
echo "1) Логи программы (app.log)"
echo "2) Логи бота (bot.log)"
echo "3) Оба лога вместе"
echo -n "Введите номер (1-3): "
read choice

case $choice in
  1)
    echo "Открываю логи программы..."
    tail -f /opt/ai-message-aggregator/app.log
    ;;
  2)
    echo "Открываю логи бота..."
    tail -f /opt/ai-message-aggregator/bot.log
    ;;
  3)
    echo "Открываю оба лога..."
    tail -f /opt/ai-message-aggregator/app.log /opt/ai-message-aggregator/bot.log
    ;;
  *)
    echo "Неверный выбор."
    ;;
esac
