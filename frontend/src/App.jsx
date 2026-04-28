import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import {
  Plane, MapPin, Calendar, Wallet, Users, Utensils,
  Send, Star, Hotel, Train, Trash2, ChevronRight,
  ChevronDown, ChevronUp, Download, Map as MapIcon, Filter, Route, Search,
  Info, Clock, Compass, Sparkles, CheckCircle, CheckCircle2, Menu, History, X
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import './App.css';

const API_BASE = "http://localhost:8000";

// High-End Tab Navigation Component
const TabNav = ({ activeTab, onTabChange }) => {
  const tabs = ['For You', 'Itinerary', 'Transport', 'Stays & Restaurants'];
  return (
    <div className="sub-nav-bar">
      {tabs.map(tab => (
        <button
          key={tab}
          className={`sub-nav-tab ${activeTab === tab ? 'active' : ''}`}
          onClick={() => onTabChange(tab)}
        >
          {tab}
        </button>
      ))}
    </div>
  );
};

const TransportLogisticsTable = ({ meta, options, selected }) => {
  if (!meta) return null;

  return (
    <div className="transport-tabular-dashboard">
      <div className="transport-section">
        <div className="ts-header"><MapPin size={18} /> Transport Details</div>
        <div className="ts-table-wrapper">
          <table className="ts-main-table">
            <thead>
              <tr>
                <th>From City</th>
                <th>From Station (Code)</th>
                <th>To City</th>
                <th>To Station (Code)</th>
                <th>Distance (km)</th>
                <th>Distance Category</th>
                <th>Area</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><div className="city-pin"><MapPin size={14} color="var(--primary)" /> {meta?.from_city}</div></td>
                <td>{meta?.from_station || "N/A"}</td>
                <td><div className="city-pin"><MapPin size={14} color="var(--primary)" /> {meta?.to_city}</div></td>
                <td>{meta?.to_station || "N/A"}</td>
                <td>{meta?.distance_km || 0}</td>
                <td><span className="dist-badge">{meta?.distance_category || "N/A"}</span></td>
                <td>{meta?.area || "N/A"}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="transport-section" style={{ marginTop: '2rem' }}>
        <div className="ts-header"><Train size={18} /> Travel Options</div>
        <div className="ts-table-wrapper">
          <table className="ts-main-table">
            <thead>
              <tr>
                <th>Mode</th>
                <th>Provider</th>
                <th>Type</th>
                <th>Train Name / Service</th>
                <th>Train Number</th>
                <th>Departure Time</th>
                <th>Cost (₹)</th>
                <th>Area / Location</th>
              </tr>
            </thead>
            <tbody>
              {options?.map((opt, idx) => {
                const isSelected = opt.train_number === selected?.train_number && opt.provider === selected?.provider;
                return (
                  <tr key={idx} className={isSelected ? "selected-row" : ""}>
                    <td>
                      <div className="mode-icon-cell">
                        {opt.mode?.toLowerCase() === 'train' ? <Train size={16} /> : <Route size={16} />}
                        {" "}{opt.mode}
                        {isSelected && <CheckCircle2 size={14} style={{ marginLeft: '4px' }} />}
                      </div>
                    </td>
                    <td>{opt.provider}</td>
                    <td>{opt.type}</td>
                    <td>{opt.train_name || "---"}</td>
                    <td>{opt.train_number || "---"}</td>
                    <td>{opt.departure_time}</td>
                    <td className="price-cell">₹{(opt.cost || 0).toLocaleString() ?? "0"}</td>
                    <td>{opt.area || meta?.area || "N/A"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

// Nested Hub Selector Component
const NestedHubSelector = ({ label, allCities, value, onChange, states, selectedState, onStateChange }) => {
  const hubs = React.useMemo(() => {
    const hubMap = {};
    allCities.filter(city => city.state === selectedState).forEach(city => {
      const parent = city.parent_hub || city.name;
      if (!hubMap[parent]) hubMap[parent] = [];
      if (city.name !== parent) {
        hubMap[parent].push(city);
      }
    });
    return hubMap;
  }, [allCities, selectedState]);

  const [expandedHub, setExpandedHub] = useState(null);

  const toggleHub = (hub, e) => {
    e.stopPropagation();
    setExpandedHub(expandedHub === hub ? null : hub);
  };

  return (
    <div className="input-group-hierarchy">
      <label>{label}</label>
      <div className="state-selectors">
        {states.map(s => (
          <label key={s} className="checkbox-label">
            <input
              type="radio"
              name={`state-${label}`}
              checked={selectedState === s}
              onChange={() => onStateChange(s)}
            />
            <span>{s}</span>
          </label>
        ))}
      </div>
      <div className="nested-hub-container">
        {Object.keys(hubs).map(hub => (
          <div key={hub} className="hub-item-container">
            <div className={`hub-main-row ${value === hub ? 'selected' : ''}`} onClick={() => onChange(hub)}>
              <div className="hub-name">
                <MapPin size={14} /> {hub}
              </div>
              {hubs[hub].length > 0 && (
                <div className="hub-dropdown-icon" onClick={(e) => toggleHub(hub, e)}>
                  {expandedHub === hub ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </div>
              )}
            </div>
            {expandedHub === hub && hubs[hub].length > 0 && (
              <div className="hub-sub-list">
                {hubs[hub].map(sub => (
                  <div
                    key={sub.city_id}
                    className={`sub-city-row ${value === sub.name ? 'selected' : ''}`}
                    onClick={() => onChange(sub.name)}
                  >
                    {sub.name}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

// Media Card Component (Rule 2)
const MediaCard = ({ item, type }) => {
  const defaultImages = {
    stay: 'https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=400&q=80',
    food: 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=400&q=80'
  };

  return (
    <motion.div
      whileHover={{ y: -5 }}
      className="media-card"
    >
      <div className="card-image" style={{ backgroundImage: `url(${item.image_url || defaultImages[type]})` }}>
        <div className="card-rating"><Star size={12} fill="currentColor" /> {item.rating || '4.5'}</div>
      </div>
      <div className="card-content">
        <h4 className="card-name">{item.name}</h4>
        <p className="card-area"><MapPin size={12} /> {item.area}</p>
        {type === 'stay' && <p className="card-price">₹{item.price_per_night?.toLocaleString()} / night</p>}
        {type === 'food' && <p className="card-cuisine">{item.cuisine || 'Local Specialty'}</p>}
      </div>
    </motion.div>
  );
};

// High-End Tabular Itinerary & Budget Component
const ItineraryTable = ({ itinerary, activeSubTab, setActiveSubTab }) => {
  if (!itinerary || !itinerary.costs || itinerary.status === 'gathering') return null;

  const renderContent = () => {
    switch (activeSubTab) {
      case 'Itinerary':
        return (
          <div className="itinerary-table-wrapper">
            <table className="itinerary-main-table">
              <thead>
                <tr>
                  <th style={{ width: '80px' }}>Day</th>
                  <th>Plans of the Day</th>
                  <th style={{ width: '220px' }}>Meal & Stay</th>
                </tr>
              </thead>
              <tbody>
                {itinerary.itinerary_days.map((day, idx) => (
                  <tr key={idx}>
                    <td className="day-cell">
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                        <span style={{ fontSize: '0.9rem', fontWeight: '600' }}>Day {day.day}</span>
                      </div>
                    </td>
                    <td className="slot-cell">
                      <div className="day-plan-text" style={{ fontSize: '0.95rem', fontWeight: '500', color: 'var(--text-main)' }}>
                        {day.daily_activity || day.activities_list}
                      </div>
                    </td>
                    <td className="stay-cell">
                      <div className="meal-name"><Utensils size={12} /> {day.meal}</div>
                      <div className="hotel-name"><Hotel size={12} /> {day.stay}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      case 'Transport':
        return <TransportLogisticsTable meta={itinerary?.transport_meta} options={itinerary?.available_transport} selected={itinerary?.selected_transport} />;
      case 'Stays & Restaurants':
        return (
          <div className="media-grid">
            {itinerary.media_cards?.stays.map((hotel, i) => (
              <MediaCard key={`stay-${i}`} item={hotel} type="stay" />
            ))}
            {itinerary.media_cards?.restaurants.map((food, i) => (
              <MediaCard key={`food-${i}`} item={food} type="food" />
            ))}
          </div>
        );
      default:
        const rooms = Math.ceil(itinerary.travellers / itinerary.selected_hotel.max_people);
        const foodEntrySum = itinerary.costs.food + itinerary.costs.activities;
        const remaining = itinerary.kpi?.remaining;

        return (
          <div className="for-you-dashboard">
            <div className="dashboard-table-header">
              <div className="col-cat">Category</div>
              <div className="col-det">Detailed Plan</div>
              <div className="col-cost">Cost</div>
            </div>

            {/* Transport Card */}
            <div className="dashboard-card-row">
              <div className="col-cat">
                <div className="cat-label">
                  {itinerary.selected_transport.mode?.toLowerCase() === 'cab' ? <Compass size={16} /> :
                    (itinerary.selected_transport.mode?.toLowerCase() === 'bus' ? <Route size={16} /> : <Train size={16} />)}
                  {" "}{itinerary.selected_transport.mode || "Transport"}
                </div>
              </div>
              <div className="col-det">
                <div className="det-title">Board {itinerary.selected_transport.provider || itinerary.selected_transport.train_name} from {itinerary.selected_transport.from_station} — {itinerary.selected_transport.class}</div>
                <div className="det-sub">₹{(itinerary.selected_transport.cost || 0).toLocaleString()} x {itinerary.travellers} travellers x 2 (Round Trip)</div>
              </div>
              <div className="col-cost">₹{(itinerary.costs.transport || 0).toLocaleString()}</div>
            </div>

            {/* Stay Card */}
            <div className="dashboard-card-row">
              <div className="col-cat">
                <div className="cat-label"><Hotel size={16} /> Hotel ({itinerary.selected_hotel.rating}★)</div>
              </div>
              <div className="col-det">
                <div className="det-title">{itinerary.selected_hotel.name} in {itinerary.selected_hotel.area} — {rooms} Rooms for {itinerary.travellers} People</div>
                <div className="det-sub">₹{itinerary.selected_hotel.price_per_night} x {rooms} rooms x {itinerary.days} nights</div>
              </div>
              <div className="col-cost">₹{(itinerary.costs.hotel || 0).toLocaleString()}</div>
            </div>

            {/* Dining & Activity Card */}
            <div className="dashboard-card-row">
              <div className="col-cat">
                <div className="cat-label"><Utensils size={16} /> Food & Activity</div>
              </div>
              <div className="col-det">
                <div className="det-title">Meals at {itinerary.media_cards?.restaurants?.[0]?.name || "Local Eatery"} + Entry Fees</div>
                <div className="det-sub">₹{(foodEntrySum || 0).toLocaleString()} combined estimate</div>
              </div>
              <div className="col-cost">₹{(foodEntrySum || 0).toLocaleString()}</div>
            </div>

            {/* KPI Footer */}
            <div className="kpi-footer-bar">
              <div className="kpi-total-section">
                <span className="kpi-label">TOTAL<br />Estimated Cost</span>
                <span className="kpi-value">₹{itinerary.kpi?.spent?.toLocaleString()}</span>
              </div>
              <div className="kpi-status-section">
                <div className="status-label">STATUS</div>
                <div className={`status-badge ${remaining >= 0 ? 'safe' : 'adjusted'}`}>
                  {remaining >= 0 ? "Budget Safe ✅" : "Adjusted to Fit ⚠️"}
                </div>
                <div className="kpi-remaining">Remaining: ₹{remaining?.toLocaleString()}</div>
              </div>
            </div>
          </div>
        );
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="professional-itinerary-container"
    >
      <div className="itinerary-header">
        <div className="header-top">
          <span className="plan-badge">BEST TRAVEL PLAN</span>
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
            <h2 className="dest-title">Journey to {itinerary?.destination || "Destination"}</h2>
          </div>
        </div>
        <TabNav activeTab={activeSubTab} onTabChange={setActiveSubTab} />
      </div>

      <div className="tab-content-area">
        {renderContent()}
      </div>

      <div className="budget-summary-card">
        <div className="card-label">BUDGET SUMMARY</div>
        <div className="budget-grid">
          <div className="budget-item">
            <span className="label">Transport ({itinerary.selected_transport?.class || "N/A"})</span>
            <span className="value">₹{itinerary.costs?.transport?.toLocaleString() || "0"}</span>
          </div>
          <div className="budget-item">
            <span className="label">Hotel Stay ({itinerary.selected_hotel?.rating || "0"}★)</span>
            <span className="value">₹{itinerary.costs?.hotel?.toLocaleString() || "0"}</span>
          </div>
          <div className="budget-item">
            <span className="label">Food preferred </span>
            <span className="value">₹{itinerary.costs?.food?.toLocaleString() || "0"}</span>
          </div>
          <div className="budget-item">
            <span className="label">Activities</span>
            <span className="value">₹{itinerary.costs?.activities?.toLocaleString() || "0"}</span>
          </div>
          <div className="budget-total">
            <div className="total-row">
              <span className="label">Total Estimated</span>
              <span className="value">₹{itinerary.costs?.total?.toLocaleString() || "0"}</span>
            </div>
            <div className="remaining-row">
              <span className="label">Remaining Budget</span>
              <span className="value highlight">₹{((itinerary?.budget || 0) - (itinerary?.costs?.total || 0)).toLocaleString() ?? "0"}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="itinerary-footer">
        <Info size={14} />
        <span>Prices are estimated based on current market data and availability.</span>
      </div>
    </motion.div>
  );
};

function App() {
  const [activeTab, setActiveTab] = useState('Filters');
  const [activeSubTab, setActiveSubTab] = useState('For You');
  const [messages, setMessages] = useState([
    { role: 'assistant', content: "Hi there! I'm your professional travel assistant. I can help you plan trips across Tamil Nadu, Kerala, Karnataka, Andhra Pradesh, and Telangana. Where would you like to go?" }
  ]);
  const [input, setInput] = useState("");
  const [formData, setFormData] = useState({
    from_state: '',
    from_hub: '',
    to_state: '',
    destination: '',
    travel_month_mode: 'Choose',
    travel_month: 'Choose a month',
    days: 0,
    budget: 0,
    trip_type: 'Choose',
    travellers: 0,
    food_preference: 'Both',
    travel_mood: 'Choose'
  });

  const [moodData, setMoodData] = useState({ travel_moods: [], city_mood_mapping: {} });
  const [hubs, setHubs] = useState([]);
  const [destCities, setDestCities] = useState([]);
  const [states] = useState(['Tamil Nadu', 'Kerala', 'Karnataka', 'Telangana', 'Andhra Pradesh']);
  const [itinerary, setItinerary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [accordions, setAccordions] = useState({ accommodation: true, food: false });
  const scrollRef = useRef(null);


  const [allCities, setAllCities] = useState([]);

  // App State additions for History and Weather
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarView, setSidebarView] = useState('filters'); // 'filters' or 'history'
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState(null);

  useEffect(() => {
    document.title = "TravelPlanner";
    setSessionId(`sess_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`);
  }, []);


  const loadHistory = async () => {
    try {
      const res = await axios.get(`${API_BASE}/sessions`);
      setSessions(res.data);
    } catch (err) { console.error(err); }
  };

  const toggleSidebar = () => {
    if (sidebarCollapsed) {
      setSidebarCollapsed(false);
    } else {
      setSidebarCollapsed(true);
    }
  };

  const handleOpenHistory = async () => {
    setSidebarView('history');
    setSidebarCollapsed(false);
    await loadHistory();
  };

  const handleOpenFilters = () => {
    setSidebarView('filters');
    setSidebarCollapsed(false);
  };

  const loadSession = async (id) => {
    try {
      const res = await axios.get(`${API_BASE}/sessions/${id}`);
      setSessionId(id);
      setMessages(res.data.messages || []);
      if (res.data.plan_metadata && res.data.plan_metadata.status === 'done') {
        setItinerary(res.data.plan_metadata);

        // Full Context Handoff
        setActiveTab('Itinerary');
        setActiveSubTab('For You');

        // Restore formData to prevent coordinate leakage/mismatch
        setFormData(prev => ({
          ...prev,
          destination: res.data.plan_metadata.destination || prev.destination,
          days: res.data.plan_metadata.days || prev.days,
          budget: res.data.plan_metadata.budget || prev.budget,
          travel_month: res.data.plan_metadata.travel_month || prev.travel_month,
          travellers: res.data.plan_metadata.travellers || prev.travellers,
          trip_type: res.data.plan_metadata.trip_type || prev.trip_type,
          from_hub: res.data.plan_metadata.origin || prev.from_hub,
          from_state: res.data.plan_metadata.from_state || prev.from_state
        }));
      }
    } catch (err) { console.error(err); }
  };

  const handleDeleteSession = async (e, id) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this journey?")) return;
    try {
      await axios.delete(`${API_BASE}/sessions/${id}`);
      setSessions(prev => prev.filter(s => s.session_id !== id));
      if (sessionId === id) {
        setItinerary(null);
        setMessages([{ role: 'assistant', content: "Session deleted. How can I help you start a new journey?" }]);
      }
    } catch (err) { console.error("Deletion failed", err); }
  };

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Fetch all cities for Nested Hub Logic
  useEffect(() => {
    const fetchAllCities = async () => {
      try {
        const res = await axios.get(`${API_BASE}/cities`);
        setAllCities(res.data);
      } catch (err) { console.error(err); }
    };
    const fetchMoods = async () => {
      try {
        const res = await axios.get(`${API_BASE}/moods`);
        setMoodData(res.data);
      } catch (err) { console.error(err); }
    };
    fetchAllCities();
    fetchMoods();
    loadHistory(); // Boot-Load History
  }, []);

  const filteredDestCities = React.useMemo(() => {
    if (!formData.travel_mood || !moodData?.city_mood_mapping) return allCities;
    const allowedCityIds = Object.keys(moodData.city_mood_mapping).filter(id =>
      moodData.city_mood_mapping[id].includes(formData.travel_mood)
    ).map(Number);
    return allCities.filter(c => allowedCityIds.includes(c.city_id));
  }, [allCities, formData.travel_mood, moodData]);

  const toggleAccordion = (key) => {
    setAccordions(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const processResponse = async (data, currentMsgs = []) => {
    setItinerary(data);
    // Clean text of [MAP_CONFIG]
    let cleanText = data.final_response || "";
    cleanText = cleanText.replace(/\[MAP_CONFIG\][\s\S]*?\[\/MAP_CONFIG\]/g, '');

    const assistantMsg = {
      role: 'assistant',
      content: cleanText,
      itinerary: data.status === 'done' ? data : null
    };

    const updatedMsgs = [...currentMsgs, assistantMsg];
    setMessages(updatedMsgs);

    // PERSISTENCE SYNC: Save every interaction to backend
    try {
      await axios.post(`${API_BASE}/sessions`, {
        session_id: sessionId,
        title: data.destination ? `Journey to ${data.destination}` : "New Journey",
        messages: updatedMsgs,
        plan_metadata: data
      });
      await loadHistory();
    } catch (err) { console.error("Session save failed", err); }

    if (data.status === 'done') {
      setActiveSubTab('For You');
      setFormData(prev => ({
        ...prev,
        destination: data.destination || prev.destination,
        days: data.days || prev.days,
        budget: data.budget || prev.budget,
        travel_month: data.travel_month || prev.travel_month,
        trip_type: data.trip_type || prev.trip_type,
        travellers: data.travellers || prev.travellers,
        budget_updated: data.budget_updated || false
      }));
    }
  };

  const handlePlanTrip = async (e) => {
    if (e) e.preventDefault();

    // Travel Month UX Guardrails
    if (formData.travel_month_mode === 'Choose' && (formData.travel_month === 'Choose a month' || !formData.travel_month)) {
      setMessages(prev => [...prev, { role: 'assistant', content: "Please select a specific month or choose 'Suggest by AI' to proceed with your itinerary." }]);
      return;
    }

    // Strict Relational Lock: Ensure required fields are filled
    if (!formData.destination || !formData.from_hub) {
      const missing = !formData.from_hub ? "Starting City" : "Destination";
      setMessages(prev => [...prev, { role: 'assistant', content: `Please select a ${missing} to proceed with the itinerary.` }]);
      return;
    }

    setLoading(true);
    try {
      const monthParam = formData.travel_month_mode === 'Suggest by AI' ? 'Suggest by AI' : formData.travel_month;
      const userQuery = `Plan a ${formData.days} day trip to ${formData.destination} from ${formData.from_hub} in ${monthParam}`;

      const msgsWithUser = [...messages, { role: 'user', content: userQuery }];
      setMessages(msgsWithUser);

      const res = await axios.post(`${API_BASE}/plan`, {
        query: userQuery,
        ...formData,
        origin: formData.from_hub,
        travel_month: monthParam
      });
      processResponse(res.data, msgsWithUser);
    } catch (err) {
      console.error(err);
      setMessages(prev => [...prev, { role: 'assistant', content: "I encountered a data mismatch while planning this route. Let me try an alternative approach." }]);
    }
    setLoading(false);
  };

  const handleChatSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMsg = input;
    const newUserMessage = { role: 'user', content: userMsg };
    const msgsWithUser = [...messages, newUserMessage];
    setMessages(msgsWithUser);

    setInput("");
    setLoading(true);

    try {
      const res = await axios.post(`${API_BASE}/plan`, {
        query: userMsg,
        ...formData
      });
      processResponse(res.data, msgsWithUser);

    } catch (err) {
      console.error(err);
      setMessages(prev => [...prev, { role: 'assistant', content: "I encountered a data mismatch while planning this route. Let me try an alternative approach." }]);
    }
    setLoading(false);
  };

  return (
    <div className={`app-container ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      {/* Column 1: Sidebar */}
      <aside className="sidebar">
        <div className="logo" style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
          {sidebarCollapsed ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', alignItems: 'center', width: '100%', padding: '1rem 0' }}>
              <Menu className="logo-icon" size={28} style={{ cursor: 'pointer', marginBottom: '2rem' }} onClick={toggleSidebar} />
              <Filter size={24} style={{ cursor: 'pointer', color: sidebarView === 'filters' ? 'var(--primary)' : 'var(--text-muted)' }} onClick={handleOpenFilters} />
              <History size={24} style={{ cursor: 'pointer', color: sidebarView === 'history' ? 'var(--primary)' : 'var(--text-muted)' }} onClick={handleOpenHistory} />
            </div>
          ) : (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <MapPin className="logo-icon" size={32} />
                <span>Travel<span style={{ color: 'var(--primary)' }}>Planner</span></span>
              </div>
              <Menu size={24} style={{ cursor: 'pointer', color: 'var(--text-muted)' }} onClick={toggleSidebar} />
            </>
          )}
        </div>

        {!sidebarCollapsed && (
          <div className="tabs">
            <button className={`tab ${sidebarView === 'filters' ? 'active' : ''}`} onClick={handleOpenFilters}>
              <Filter size={16} /> Filters
            </button>
            <button className={`tab ${sidebarView === 'history' ? 'active' : ''}`} onClick={handleOpenHistory}>
              <History size={16} /> Chat logs
            </button>
          </div>
        )}

        {!sidebarCollapsed && (
          <div className="sidebar-scrollable">
            {sidebarView === 'filters' ? (
              <div className="sidebar-content">
                <div className="input-group">
                  <label>SEARCH DESTINATION</label>
                  <div className="search-input-wrapper">
                    <Search size={18} className="search-icon" />
                    <input placeholder="Enter your destination..." value={formData.destination} name="destination" onChange={handleInputChange} />
                  </div>
                </div>

                <div className="accordion">
                  <div className="accordion-header" onClick={() => toggleAccordion('accommodation')}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><Hotel size={18} color="#6366f1" /> Accommodation</span>
                    {accordions.accommodation ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                  </div>
                  {accordions.accommodation && (
                    <div className="accordion-content">
                      <div className="input-group">
                        <label>TRIP STYLE</label>
                        <select name="trip_type" value={formData.trip_type} onChange={handleInputChange}>
                          <option value="">Select Trip Style</option>
                          <option value="solo">Solo Adventure</option>
                          <option value="couple">Romantic Couple</option>
                          <option value="family">Family Gathering</option>
                          <option value="friends">Friends Group</option>
                        </select>
                      </div>
                    </div>
                  )}
                </div>

                <div className="accordion">
                  <div className="accordion-header" onClick={() => toggleAccordion('food')}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><Utensils size={18} color="#f43f5e" /> Food & Drink</span>
                    {accordions.food ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                  </div>
                  {accordions.food && (
                    <div className="accordion-content">
                      <div className="chip-group">
                        {['Veg', 'Non-Veg', 'Both'].map(pref => (
                          <button
                            key={pref}
                            className={`chip ${formData.food_preference === pref ? 'active' : ''}`}
                            onClick={() => setFormData(prev => ({ ...prev, food_preference: pref }))}
                          >
                            {pref}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <NestedHubSelector
                  label="DEPARTING FROM"
                  allCities={allCities}
                  value={formData.from_hub}
                  onChange={(val) => setFormData(prev => ({ ...prev, from_hub: val }))}
                  states={states}
                  selectedState={formData.from_state}
                  onStateChange={(s) => setFormData(prev => ({ ...prev, from_state: s }))}
                />

                <div className="input-group">
                  <label>TRAVEL MOOD (OPTIONAL)</label>
                  <select name="travel_mood" value={formData.travel_mood} onChange={handleInputChange}>
                    <option value="">Choose a mood</option>
                    {moodData.travel_moods.map(m => (
                      <option key={m.mood_id} value={m.mood_id}>{m.name}</option>
                    ))}
                  </select>
                </div>

                <NestedHubSelector
                  label="SELECT DESTINATION"
                  allCities={filteredDestCities}
                  value={formData.destination}
                  onChange={(val) => setFormData(prev => ({ ...prev, destination: val }))}
                  states={states}
                  selectedState={formData.to_state}
                  onStateChange={(s) => setFormData(prev => ({ ...prev, to_state: s }))}
                />

                <div className="input-group">
                  <label>TRAVEL MONTH</label>
                  <select name="travel_month_mode" value={formData.travel_month_mode} onChange={handleInputChange}>
                    <option value="Choose">Choose Month</option>
                    <option value="Suggest by AI">Suggest by AI</option>
                  </select>
                  {formData.travel_month_mode === 'Choose' && (
                    <select name="travel_month" value={formData.travel_month} onChange={handleInputChange} style={{ marginTop: '8px' }}>
                      <option disabled value="Choose a month">Choose a month</option>
                      {['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'].map(m => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  )}
                </div>

                <div className="input-row-split">
                  <div className="input-group">
                    <label>DAYS</label>
                    <input type="number" name="days" value={formData.days} onChange={handleInputChange} min="1" />
                  </div>
                  <div className="input-group">
                    <label>PEOPLE</label>
                    <input type="number" name="travellers" value={formData.travellers} onChange={handleInputChange} min="1" />
                  </div>
                </div>

                <div className="input-group">
                  <label>TOTAL BUDGET (₹ {(formData.budget || 0).toLocaleString()})</label>
                  <input type="range" name="budget" min="5000" max="100000" step="1000" value={formData.budget} onChange={handleInputChange} />
                </div>

                {itinerary && itinerary.kpi && (
                  <div className="kpi-dashboard">
                    <div className="kpi-card">
                      <div className="kpi-label">TOTAL</div>
                      <div className="kpi-value">₹{(itinerary.kpi.total_budget || 0).toLocaleString()}</div>
                    </div>
                    <div className="kpi-card">
                      <div className="kpi-label">SPENT</div>
                      <div className="kpi-value highlight">₹{(itinerary.kpi.spent || 0).toLocaleString()}</div>
                    </div>
                  </div>
                )}
              </div>
            ) : sidebarView === 'history' ? (
              <div className="sidebar-content history-list">
                <h4 style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '1rem' }}>Previous Trips</h4>
                {sessions.length === 0 && <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>No previous trips found.</div>}
                {sessions.map(s => (
                  <div key={s.session_id} className="history-item" onClick={() => loadSession(s.session_id)} style={{ position: 'relative' }}>
                    <div className="history-content">
                      <div className="history-title">{s.title}</div>
                      <div className="history-date">
                        {new Date(s.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}, {new Date(s.created_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })}
                      </div>
                    </div>
                    <button
                      className="delete-history-btn"
                      onClick={(e) => handleDeleteSession(e, s.session_id)}
                      title="Delete Journey"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        )}

        {!sidebarCollapsed && sidebarView === 'filters' && (
          <div className="sidebar-actions">
            <button className="btn-secondary" onClick={() => window.print()}>
              <Download size={18} /> Download PDF
            </button>
            <button className="btn-primary" onClick={handlePlanTrip} disabled={loading}>
              {loading ? 'Optimizing Itinerary...' : 'Generate Itinerary'}
            </button>
          </div>
        )}
      </aside>

      {/* Column 2: Chat & Results - REDESIGNED */}
      <main className="chat-column">
        <header className="chat-header-bar">
          <div className="destination-title">
            {itinerary?.destination ? `Planning for ${itinerary.destination}` : "Travel Assistant"}
          </div>
        </header>

        <div className="chat-body" ref={scrollRef}>
          <div className="message-list">
            {messages.map((m, i) => (
              <div key={i}>
                <motion.div
                  initial={{ opacity: 0, x: m.role === 'user' ? 20 : -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  className={`chat-bubble-container ${m.role === 'user' ? 'user' : 'assistant'}`}
                >
                  <div className={`chat-bubble ${m.role === 'user' ? 'user' : 'assistant'}`}>
                    <div className="bubble-text">{m.content}</div>
                  </div>
                </motion.div>
                {m.itinerary && m.itinerary.status === 'done' && (
                  <ItineraryTable
                    itinerary={m.itinerary}
                    activeSubTab={activeSubTab}
                    setActiveSubTab={setActiveSubTab}
                  />
                )}
              </div>
            ))}
            {loading && (
              <div className="chat-bubble assistant">
                <motion.div
                  animate={{ opacity: [0.4, 1, 0.4] }}
                  transition={{ repeat: Infinity, duration: 1.5 }}
                >
                  ...
                </motion.div>
              </div>
            )}
          </div>
        </div>

        <div className="chat-footer">
          <form className="chat-input-form" onSubmit={handleChatSubmit}>
            <input placeholder="Type your travel request here..." value={input} onChange={(e) => setInput(e.target.value)} />
            <button type="submit" disabled={loading}><Send size={24} /></button>
          </form>
        </div>
      </main>



      {/* Hidden Print Structure - REDESIGNED AS PROFESSIONAL VOUCHER */}
      {itinerary && itinerary.status === 'done' && (
        <div className="printable-pdf-content">
          <div className="pdf-header">
            <h1 style={{ fontSize: '2.5rem', marginBottom: '0.5rem', color: '#1e293b' }}>Journey to {itinerary.destination}</h1>
            <div style={{ display: 'flex', gap: '2rem', marginBottom: '2rem', borderBottom: '2px solid #e2e8f0', paddingBottom: '1rem' }}>
              <div><strong>Plan Summary:</strong></div>
              <div>Budget: ₹{itinerary.budget?.toLocaleString()}</div>
              <div>Duration: {itinerary.days} Days</div>
              <div>Travelers: {itinerary.travellers} Adults</div>
              <div>Mood: {formData.travel_mood ? moodData.travel_moods.find(m => m.mood_id === formData.travel_mood)?.name || formData.travel_mood : 'General'}</div>
            </div>
          </div>

          <div className="pdf-section">
            <h2 style={{ borderLeft: '4px solid #6366f1', paddingLeft: '1rem', marginBottom: '1rem' }}>Travel Logistics</h2>
            <table className="print-table">
              <thead>
                <tr>
                  <th>From ➔ To Station</th>
                  <th>Service (No.)</th>
                  <th>Mode / Provider</th>
                  <th>Departure</th>
                  <th>Cost (Est.)</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{itinerary.selected_transport.from_station} ➔ {itinerary.selected_transport.to_station}</td>
                  <td>{itinerary.selected_transport.train_name || 'N/A'} ({itinerary.selected_transport.train_number || 'N/A'})</td>
                  <td>{itinerary.selected_transport.mode} / {itinerary.selected_transport.provider}</td>
                  <td>{itinerary.selected_transport.departure_time}</td>
                  <td>₹{itinerary.costs.transport?.toLocaleString()}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="pdf-section">
            <h2 style={{ borderLeft: '4px solid #6366f1', paddingLeft: '1rem', marginBottom: '1rem' }}>Daily Itinerary</h2>
            <table className="print-table">
              <thead>
                <tr>
                  <th style={{ width: '10%' }}>Day</th>
                  <th style={{ width: '45%' }}>Planned Activity</th>
                  <th style={{ width: '45%' }}>Meals & Accommodation</th>
                </tr>
              </thead>
              <tbody>
                {itinerary.itinerary_days.map((d, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 'bold' }}>Day {d.day}</td>
                    <td>{d.daily_activity}</td>
                    <td>
                      <div style={{ fontSize: '0.9rem' }}>🍽️ {d.meal}</div>
                      <div style={{ fontSize: '0.9rem', color: '#64748b' }}>🏨 {d.stay}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Page break before budget if itinerary is long */}
          <div style={{ pageBreakBefore: itinerary.days > 4 ? 'always' : 'auto', marginTop: '2rem' }}>
            <h2 style={{ borderLeft: '4px solid #10b981', paddingLeft: '1rem', marginBottom: '1rem' }}>Budget Breakdown (KPI)</h2>
            <table className="print-table" style={{ width: '100%', maxWidth: '500px' }}>
              <tbody>
                <tr>
                  <td><strong>Total Allocated Budget</strong></td>
                  <td style={{ textAlign: 'right' }}>₹{itinerary.budget?.toLocaleString()}</td>
                </tr>
                <tr>
                  <td><strong>Estimated Total Spent</strong></td>
                  <td style={{ textAlign: 'right', fontWeight: 'bold', color: '#ef4444' }}>₹{itinerary.costs.total?.toLocaleString()}</td>
                </tr>
                <tr style={{ backgroundColor: '#f8fafc' }}>
                  <td><strong>Remaining Balance</strong></td>
                  <td style={{ textAlign: 'right', fontWeight: 'bold', color: '#10b981' }}>₹{(itinerary.budget - itinerary.costs.total).toLocaleString()}</td>
                </tr>
              </tbody>
            </table>
            <p style={{ fontSize: '0.8rem', color: '#94a3b8', marginTop: '1rem' }}>
              Note: Remaining balance includes a 10% emergency buffer reserved for miscellaneous expenses.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
