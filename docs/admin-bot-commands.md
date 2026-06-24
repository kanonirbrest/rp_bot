# Команды бота для администратора

Доступ только при `user_id` в **`ADMIN_IDS`** в `.env` (через запятую). Иначе бот не отвечает.

| Команда | Что делает |
|---------|------------|
| `/stats` | Статистика: число пользователей и последние 5 регистраций |
| `/export` | CSV со всеми контактами из базы |
| `/reviews` | Последние 10 отзывов в чате |
| `/exportreviews` | Файл `reviews.csv` — все отзывы |
| `/qr` | QR-код на старт бота (нужен пакет `qrcode[pil]`) |
| `/qrzone` | Подсказка и список зон; `/qrzone <номер>` — QR на карту выставки для зоны |
| `/setphoto` | Задать фото раздела «Анонсы» (фото + в подписи `/setphoto`) |
| `/setgif` | GIF для розыгрыша (гифка + в подписи `/setgif`) |
| `/setmainphoto` | Фото главного меню (фото + `/setmainphoto`) |
| `/setexhibitionphoto` | Фото раздела выставки (фото + `/setexhibitionphoto`) |
| `/setcertphoto` | Фото раздела сертификатов (фото + `/setcertphoto`) |
| `/setaboutphoto` | Фото блока «О RAZMAN production» (фото + `/setaboutphoto`) |
| `/clearaboutphoto` | Убрать фото из блока «О RAZMAN production» |
| `/broadcast` | Рассылка: текст, или фото/GIF с подписью `/broadcast …` |
| `/revokepromo NR-XXXXXXXX` | Отключить промокод **по коду** |
| `/reissuepromo <telegram_user_id>` или `/reissuepromo NR-XXXXXXXX` | Перевыдать новый активный промокод (старый код перестаёт действовать) |
| `/userpromo <telegram_user_id>` или `/userpromo NR-XXXXXXXX` | Показать код, статус и user_id (можно искать по коду) |
