import json
import os
import sqlite3
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
# import faiss
# from sentence_transformers import SentenceTransformer

class DataService:
    def __init__(self, dataset_path: str = "dataset"):
        self.dataset_path = dataset_path
        self._cities = self._load_json("cities.json", "cities")
        self._weather = self._load_json("weather.json", "weather")
        self._attractions = self._load_json("attractions.json", "attractions")
        self._hotels = self._load_json("hotels.json", "hotels")
        self._food = self._load_json("food_places.json", "food_places")
        self._transport = self._load_json("transport.json", "transport_routes")
        
        # Load travel moods
        mood_data = self._load_json_full("travel_mood.json")
        self._travel_moods = mood_data.get("travel_moods", []) if mood_data else []
        self._city_mood_mapping = mood_data.get("city_mood_mapping", {}) if mood_data else {}
        
        # SQLite Database for Chat History
        self.db_path = "travel_planner.db"
        self._init_sqlite()
        
        # RAG / Vector DB Setup (Disabled for speed/simplicity)
        # self.model = SentenceTransformer('all-MiniLM-L6-v2')
        # self.index = None
        # self.vector_data = []
        # self._initialize_vector_db()

    def _init_sqlite(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                title TEXT,
                created_at TIMESTAMP,
                messages TEXT,
                plan_metadata TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                created_at TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            )
        ''')
        conn.commit()
        conn.close()

    def save_session(self, session_id: str, title: str, messages: List[Dict[str, Any]], plan_metadata: Dict[str, Any]):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        # Save session metadata
        cursor.execute('''
            INSERT OR REPLACE INTO sessions (session_id, title, created_at, messages, plan_metadata)
            VALUES (?, ?, ?, ?, ?)
        ''', (session_id, title, now, json.dumps(messages), json.dumps(plan_metadata)))
        
        # Save individual messages for "pair" persistence verification
        # First clear old messages for this session to avoid duplicates
        cursor.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
        for msg in messages:
            cursor.execute('''
                INSERT INTO messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
            ''', (session_id, msg.get('role'), msg.get('content'), now))
            
        conn.commit()
        conn.close()

    def delete_session(self, session_id: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
        cursor.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
        conn.commit()
        conn.close()

    def get_all_sessions(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT session_id, title, created_at FROM sessions ORDER BY created_at DESC')
        rows = cursor.fetchall()
        conn.close()
        return [{"session_id": r[0], "title": r[1], "created_at": r[2]} for r in rows]

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT session_id, title, created_at, messages, plan_metadata FROM sessions WHERE session_id = ?', (session_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "session_id": row[0],
                "title": row[1],
                "created_at": row[2],
                "messages": json.loads(row[3]) if row[3] else [],
                "plan_metadata": json.loads(row[4]) if row[4] else {}
            }
        return None

    def _load_json(self, filename: str, key: str) -> List[Dict[str, Any]]:
        path = os.path.join(self.dataset_path, filename)
        if not os.path.exists(path):
            return []
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get(key, [])

    def _load_json_full(self, filename: str) -> Dict[str, Any]:
        path = os.path.join(self.dataset_path, filename)
        if not os.path.exists(path):
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _initialize_vector_db(self):
        documents = []
        # Index Attractions
        for idx, attr in enumerate(self._attractions):
            category = attr.get('category', [])
            suitable_for = attr.get('suitable_for', [])
            cat_str = f"a {', '.join(category)} attraction" if category else "an attraction"
            suitable_str = f"suitable for {', '.join(suitable_for)}" if suitable_for else "suitable for everyone"
            
            desc = f"{attr['name']} in {attr['area']} is {cat_str}. It is {'outdoor' if attr.get('outdoor', True) else 'indoor'} and {suitable_str}."
            documents.append({"text": desc, "id": f"attr_{idx}", "type": "attraction"})
        
        # Index Food
        for idx, f in enumerate(self._food):
            cuisine = f.get('cuisine', 'Varies')
            area = f.get('area', 'Local Area')
            suitable = ', '.join(f.get('suitable_for', ['Everyone']))
            desc = f"{f['name']} in {area} serves {cuisine} cuisine. Suitable for {suitable}. Average cost: {f.get('avg_cost', 'N/A')}."
            documents.append({"text": desc, "id": f"food_{idx}", "type": "food"})

        if not documents:
            return

        self.vector_data = documents
        texts = [d['text'] for d in documents]
        embeddings = self.model.encode(texts)
        
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(np.array(embeddings).astype('float32'))

    def search_descriptions(self, query: str, k: int = 3) -> List[Dict[str, Any]]:
        if self.index is None:
            return []
        query_vector = self.model.encode([query])
        distances, indices = self.index.search(np.array(query_vector).astype('float32'), k)
        
        results = []
        for idx in indices[0]:
            if idx < len(self.vector_data):
                results.append(self.vector_data[idx])
        return results

    def get_coordinates(self, type: str, id: int) -> List[float]:
        # Priority 1: Check in-memory JSON data (most accurate)
        if type == 'city':
            for city in self._cities:
                if city['city_id'] == id:
                    if 'lat' in city and 'lng' in city:
                        return [float(city['lat']), float(city['lng'])]
        elif type == 'attraction':
            for attr in self._attractions:
                if attr.get('att_id') == id:
                    if 'lat' in attr and 'lng' in attr:
                        return [float(attr['lat']), float(attr['lng'])]
        
        # Priority 2: Predefined mapping for demo / legacy support
        city_coords = {
            1: [11.4100, 76.7000],   # Ooty
            29: [10.0889, 77.0595],  # Munnar
            15: [10.2381, 77.4892],  # Kodaikanal
            18: [15.3350, 76.4600],  # Hampi
            100: [12.9165, 79.1325], # Vellore
            50: [13.0827, 80.2707],  # Chennai
            60: [12.9716, 77.5946],  # Bangalore
            70: [17.3850, 78.4867],  # Hyderabad
            80: [9.9312, 76.2673],   # Kochi
            90: [11.9416, 79.8083],  # Pondicherry
        }
        
        attr_coords = {
            9: [10.0912, 77.0610],   # Tea Museum (Munnar)
            18: [15.3350, 76.4600],  # Virupaksha Temple (Hampi)
            100: [12.9165, 79.1325], # Jalakandeswarar Fort (Vellore)
        }
        
        if type == 'city':
            return city_coords.get(id, [12.9716, 77.5946])
        return attr_coords.get(id, [12.9716, 77.5946])

    def get_all_cities(self) -> List[Dict[str, Any]]:
        return self._cities

    def get_city_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        for city in self._cities:
            if city['name'].lower() == name.lower():
                return city
        return None

    def get_weather(self, city_id: int, month: str) -> Optional[Dict[str, Any]]:
        for w in self._weather:
            if w['city_id'] == city_id and (w['month'].lower() == month.lower() or w['month'].lower() == month.lower()[:3]):
                return w
        return None

    def get_all_weather(self, city_id: int) -> List[Dict[str, Any]]:
        return [w for w in self._weather if w['city_id'] == city_id]

    def get_hotels(self, city_id: int) -> List[Dict[str, Any]]:
        return [h for h in self._hotels if h['city_id'] == city_id]

    def get_attractions(self, city_id: int) -> List[Dict[str, Any]]:
        # STRICT RELATIONAL LOCK: Only use attractions where city_id matches
        return [a for a in self._attractions if a['city_id'] == city_id]

    def get_food_places(self, city_id: int) -> List[Dict[str, Any]]:
        # STRICT RELATIONAL LOCK: Only use food places where city_id matches
        return [f for f in self._food if f['city_id'] == city_id]

    def get_cities_by_state(self, state_name: str) -> List[Dict[str, Any]]:
        return [c for c in self._cities if c['state'].lower() == state_name.lower()]

    def get_hubs_by_state(self, state_name: str) -> List[str]:
        hubs = {c['parent_hub'] for c in self._cities if c['state'].lower() == state_name.lower() and c.get('parent_hub')}
        return sorted(list(hubs))

    def get_transport(self, from_city: str, to_city: str) -> List[Dict[str, Any]]:
        return [t for t in self._transport if (t['from_city'].lower() == from_city.lower() and t['to_city'].lower() == to_city.lower())]

    def get_travel_moods(self) -> List[Dict[str, Any]]:
        return self._travel_moods

    def get_city_mood_mapping(self) -> Dict[str, List[str]]:
        return self._city_mood_mapping
