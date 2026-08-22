import sqlite3
import pandas as pd

def dump_db():
    try:
        conn = sqlite3.connect('data.db')
        
        tables = ['tg_channels', 'news_topics', 'banwords', 'ai_chat_history']
        
        for table in tables:
            print(f"\n--- Таблица: {table} ---")
            try:
                df = pd.read_sql_query(f"SELECT * FROM {table} LIMIT 10", conn)
                if df.empty:
                    print("Пусто")
                else:
                    print(df.to_string(index=False))
                    
                # Print total count
                count = pd.read_sql_query(f"SELECT COUNT(*) as c FROM {table}", conn).iloc[0]['c']
                print(f"Всего записей: {count}")
            except Exception as e:
                print(f"Ошибка чтения таблицы: {e}")
                
        conn.close()
    except Exception as e:
        print(f"Ошибка БД: {e}")

if __name__ == "__main__":
    dump_db()
