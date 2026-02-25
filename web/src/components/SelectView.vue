<template>
  <div class="select-page">

    <!-- ── Header ── -->
    <header class="select-header">
      <div class="select-header-inner">
        <!-- Logo -->
        <div class="select-logo">
          <div class="logo-icon">
            <i class="bi bi-stars"></i>
          </div>
          <div class="logo-text">
            <span class="logo-main">Mina<span class="logo-accent">Mina</span> <span class="logo-ai">AI</span></span>
            <span class="logo-sub">AI Avatar Chat</span>
          </div>
        </div>

        <!-- Search -->
        <div class="select-search">
          <i class="bi bi-search search-icon"></i>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search avatars…"
            class="search-input"
          />
        </div>

        <!-- Coins + filter -->
        <div class="select-header-right">
          <button class="coins-btn" @click="showTopUpModal = true">
            <span class="coins-icon">💎</span>
            <span class="coins-value">{{ userCoins.toLocaleString() }}</span>
          </button>
          <div class="filter-chips">
            <button
              v-for="f in filters"
              :key="f.id"
              class="filter-chip"
              :class="{ active: activeFilter === f.id }"
              @click="activeFilter = f.id"
            >{{ f.label }}</button>
          </div>
        </div>
      </div>
    </header>

    <!-- ── Scrollable content ── -->
    <div class="select-body">

      <!-- ══ HOME TAB ══ -->
      <div v-show="activeTab === 'home'">

        <!-- Avatar grid -->
        <section class="avatars-section">
          <h2 class="section-title">Your Celebrity</h2>
          <div class="avatar-grid">
            <div
              v-for="av in filteredAvatars"
              :key="av.id"
              class="avatar-card"
              :class="{ 'is-live': av.live }"
              @click="openAvatar(av)"
            >
              <div class="avatar-img-wrap">
                <img :src="av.photo" :alt="av.name" class="avatar-img"
                     @error="$event.target.src='https://placehold.co/400x600/1e293b/94a3b8?text=Avatar'">
                <div class="avatar-gradient"></div>
              </div>
              <div class="avatar-top-badges">
                <span v-if="av.live" class="live-badge">
                  <span class="live-dot"></span>LIVE
                </span>
                <span class="followers-badge">💖 {{ av.level }}</span>
              </div>
              <div class="avatar-bottom">
                <h3 class="avatar-name">{{ av.name }}</h3>
                <div class="avatar-tags">
                  <span v-for="tag in av.tags.slice(0,2)" :key="tag" class="tag">{{ tag }}</span>
                </div>
                <p class="avatar-loc">📍 {{ av.location }}</p>
              </div>
              <div class="avatar-hover-cta"><span>View Profile</span></div>
            </div>
            <div v-if="filteredAvatars.length === 0" class="empty-state">
              <div class="empty-icon">🔍</div>
              <p>No avatars found</p>
            </div>
          </div>
        </section>

        <!-- Event banners (below grid) -->
        <section class="banners-section">
          <h2 class="section-title">Featured Events</h2>
          <div class="banners-scroll">
            <div
              v-for="ev in EVENTS"
              :key="ev.id"
              class="banner-card"
              @click="openEvent(ev)"
            >
              <img :src="ev.bannerUrl" :alt="ev.title" class="banner-img"
                   @error="$event.target.src='https://placehold.co/800x150/1e293b/94a3b8?text=Event'">
              <div class="banner-overlay">
                <h3 class="banner-title">{{ ev.title }}</h3>
                <p class="banner-sub">{{ ev.subtitle }}</p>
              </div>
            </div>
          </div>
        </section>
      </div>

      <!-- ══ EVENTS TAB ══ -->
      <div v-show="activeTab === 'events'" class="tab-content">
        <div class="tab-page-header">
          <h1>Current Events</h1>
          <span>🏆</span>
        </div>
        <p class="tab-desc">Dive into the action! Participate in our time-limited campaigns to win exclusive rewards.</p>
        <div class="events-grid">
          <div
            v-for="ev in EVENTS"
            :key="ev.id"
            class="event-card"
            @click="openEvent(ev)"
          >
            <img :src="ev.fullImageUrl" :alt="ev.title" class="event-card-img"
                 @error="$event.target.src='https://placehold.co/800x300/1e293b/94a3b8?text=Event'">
            <div class="event-card-body">
              <h3 class="event-card-title">{{ ev.title }}</h3>
              <p class="event-card-sub">{{ ev.subtitle }}</p>
              <div class="event-card-footer">
                <span>📅 Ends: {{ ev.dateRange.split(' - ')[1] }}</span>
                <span class="live-now-badge">LIVE NOW</span>
              </div>
            </div>
          </div>
        </div>
        <p class="end-label">--- End of Active Events ---</p>
      </div>

      <!-- ══ FRIENDS TAB ══ -->
      <div v-show="activeTab === 'friends'" class="tab-content">
        <div class="tab-page-header">
          <h1>My Relationships</h1>
          <span>💖</span>
        </div>
        <p class="tab-desc">Track your intimacy levels, gifts sent, and status with your favorite hosts.</p>

        <h3 class="sub-heading">My Friends</h3>
        <div class="friends-list">
          <div v-for="fr in FRIENDS" :key="fr.id" class="friend-card">
            <img :src="fr.avatar" :alt="fr.name" class="friend-avatar"
                 @error="$event.target.src='https://placehold.co/64x64/1e293b/94a3b8?text=F'">
            <div class="friend-info">
              <h3>{{ fr.name }}</h3>
              <p>{{ fr.status }} · Level {{ fr.level }}</p>
              <p class="friend-gifts">🎁 Gifts Sent: {{ fr.giftsSent.toLocaleString() }}</p>
            </div>
            <button class="friend-chat-btn">💬</button>
          </div>
        </div>

        <h3 class="sub-heading" style="margin-top:2rem">Host Intimacy</h3>
        <div class="friends-list">
          <div v-for="host in hostIntimacy" :key="host.id" class="friend-card">
            <img :src="host.photo" :alt="host.name" class="friend-avatar"
                 @error="$event.target.src='https://placehold.co/64x64/1e293b/94a3b8?text=H'">
            <div class="friend-info" style="flex:1">
              <h3>{{ host.name }}</h3>
              <div class="intimacy-row">
                <span>Intimacy: {{ host.intimacy }}%</span>
                <span class="intimacy-reward">{{ host.nextReward }} Next!</span>
              </div>
              <div class="intimacy-bar-bg">
                <div class="intimacy-bar-fill" :style="{ width: host.intimacy + '%' }"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ══ PROFILE TAB ══ -->
      <div v-show="activeTab === 'profile'" class="tab-content">
        <div class="tab-page-header">
          <h1>My Profile</h1>
          <span>⚙️</span>
        </div>
        <div class="profile-card">
          <img src="https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?q=80&w=400"
               alt="User" class="profile-avatar"
               @error="$event.target.src='https://placehold.co/96x96/1e293b/94a3b8?text=U'">
          <h2 class="profile-name">GuestUser1234</h2>
          <p class="profile-id">ID: u-98d0f7a6</p>
          <div class="profile-badges">
            <span class="profile-badge level">Level 15</span>
            <span class="profile-badge vip">VIP Member</span>
          </div>
          <div class="profile-stats">
            <div class="stat"><span class="stat-val pink">15,450</span><span class="stat-lbl">Gifts Sent</span></div>
            <div class="stat"><span class="stat-val gold">{{ userCoins.toLocaleString() }}</span><span class="stat-lbl">My Coins 💎</span></div>
            <div class="stat"><span class="stat-val">92</span><span class="stat-lbl">Days Active</span></div>
          </div>
        </div>

        <h3 class="sub-heading" style="margin-top:1.5rem">Account &amp; Settings</h3>
        <div class="settings-list">
          <button class="settings-row" @click="showTopUpModal = true">
            <span><span class="settings-icon">💳</span> Top Up Coins</span>
            <span class="settings-arrow">›</span>
          </button>
          <button class="settings-row">
            <span><span class="settings-icon">👤</span> Edit Profile Info</span>
            <span class="settings-arrow">›</span>
          </button>
          <button class="settings-row">
            <span><span class="settings-icon">🔔</span> Notification Settings</span>
            <span class="settings-arrow">›</span>
          </button>
          <button class="settings-row">
            <span><span class="settings-icon">🔒</span> Privacy &amp; Security</span>
            <span class="settings-arrow">›</span>
          </button>
          <button class="settings-row">
            <span><span class="settings-icon">❓</span> Help &amp; Support</span>
            <span class="settings-arrow">›</span>
          </button>
        </div>
        <button class="signout-btn">Sign Out</button>
      </div>

    </div><!-- /.select-body -->

    <!-- ── Bottom Tab Bar ── -->
    <nav class="bottom-tab-bar">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="bottom-tab-btn"
        :class="{ active: activeTab === tab.id }"
        @click="activeTab = tab.id"
      >
        <span class="tab-icon">{{ tab.icon }}</span>
        <span class="tab-label">{{ tab.label }}</span>
      </button>
    </nav>

    <!-- ══ AVATAR DETAIL MODAL ══ -->
    <transition name="modal">
      <div v-if="selectedAvatar" class="modal-backdrop" @click.self="selectedAvatar = null">
        <div class="avatar-modal">
          <div class="avatar-modal-img-wrap">
            <img :src="selectedAvatar.photo" :alt="selectedAvatar.name" class="avatar-modal-img"
                 @error="$event.target.src='https://placehold.co/400x300/1e293b/94a3b8?text=Avatar'">
            <div class="avatar-modal-gradient"></div>
            <button class="modal-close-btn" @click="selectedAvatar = null">
              <i class="bi bi-x-lg"></i>
            </button>
            <span v-if="selectedAvatar.live" class="modal-live-badge">
              <span class="live-dot"></span>LIVE
            </span>
          </div>
          <div class="avatar-modal-body">
            <div class="modal-name-row">
              <div>
                <h2 class="modal-name">{{ selectedAvatar.name }}</h2>
                <p class="modal-meta">Age {{ selectedAvatar.age }} · {{ selectedAvatar.location }}</p>
              </div>
              <div class="modal-followers">
                <i class="bi bi-heart-fill" style="color:#f472b6"></i>
                {{ selectedAvatar.level }}
              </div>
            </div>
            <p class="modal-bio">{{ selectedAvatar.bio }}</p>
            <div class="modal-tags">
              <span v-for="tag in selectedAvatar.tags" :key="tag" class="modal-tag">{{ tag }}</span>
            </div>
            <div class="modal-intimacy">
              <div class="intimacy-label-row">
                <span>Intimacy</span>
                <span class="intimacy-pct">{{ selectedAvatar.intimacy }}%</span>
              </div>
              <div class="intimacy-bar-bg">
                <div class="intimacy-bar-fill" :style="{ width: selectedAvatar.intimacy + '%' }"></div>
              </div>
              <p class="intimacy-next">🎁 Next reward: {{ selectedAvatar.nextReward }}</p>
            </div>
            <button
              class="start-chat-btn"
              :class="{ 'is-live': selectedAvatar.live }"
              @click="startChat(selectedAvatar)"
            >
              {{ selectedAvatar.live ? '🎙️ Start Live Chat' : 'Start Chatting' }}
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- ══ EVENT DETAIL MODAL ══ -->
    <transition name="modal">
      <div v-if="selectedEvent" class="modal-backdrop" @click.self="selectedEvent = null">
        <div class="event-modal">
          <div class="event-modal-header">
            <button class="modal-close-btn-inline" @click="selectedEvent = null">✖️</button>
          </div>
          <img :src="selectedEvent.fullImageUrl" :alt="selectedEvent.title" class="event-modal-img"
               @error="$event.target.src='https://placehold.co/800x300/1e293b/94a3b8?text=Event'">
          <h2 class="event-modal-title">{{ selectedEvent.title }}</h2>
          <p class="event-modal-sub">{{ selectedEvent.subtitle }}</p>
          <div class="event-modal-meta">
            <span>📅 {{ selectedEvent.dateRange }}</span>
            <span>⭐ {{ selectedEvent.participants.toLocaleString() }} Participants</span>
          </div>
          <p class="event-modal-desc">{{ selectedEvent.description }}</p>
          <button class="join-btn">Join Event Now!</button>
        </div>
      </div>
    </transition>

    <!-- ══ TOP UP MODAL ══ -->
    <transition name="modal">
      <div v-if="showTopUpModal" class="modal-backdrop" @click.self="showTopUpModal = false">
        <div class="topup-modal">
          <h2 class="topup-title">💎 Coin Top-Up</h2>
          <div class="topup-options">
            <div class="topup-option" @click="buyCoins(10000)">
              <span class="topup-amount">10,000 💎</span>
              <span class="topup-price">$2.00</span>
            </div>
            <div class="topup-option" @click="buyCoins(50000)">
              <span class="topup-amount">50,000 💎</span>
              <span class="topup-price">$8.00</span>
            </div>
            <div class="topup-option best" @click="buyCoins(200000)">
              <span class="topup-best-tag">Best Value</span>
              <span class="topup-amount">200,000 💎</span>
              <span class="topup-price">$22.00</span>
            </div>
          </div>
          <button class="topup-cancel" @click="showTopUpModal = false">Cancel</button>
        </div>
      </div>
    </transition>

    <!-- ══ DAILY REWARD MODAL ══ -->
    <transition name="modal">
      <div v-if="showDailyReward" class="modal-backdrop">
        <div class="daily-modal">
          <h2 class="daily-title">Daily Login Bonus!</h2>
          <p class="daily-streak">Day 3 Streak!</p>
          <div class="daily-gift">🎁</div>
          <div class="daily-reward-box">
            + 5,000 <span style="color:#f59e0b">💎</span> Coins
          </div>
          <button class="daily-claim-btn" @click="claimDailyReward">CLAIM REWARD</button>
        </div>
      </div>
    </transition>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

// ── Emits ────────────────────────────────────────────────────────────────────
const emit = defineEmits(['avatar-selected'])

// ── Data ─────────────────────────────────────────────────────────────────────
const AVATARS = [
  { id: 10, name: '弥生みづき', age: 21, bio: 'Live Streamer. Voice/Text mode available.', photo: '/select/girl1.jpg', level: '50,000', location: 'Japan', tags: ['#Live', '#Cute', '#VoiceMode'], intimacy: 25, nextReward: 'Special Video', live: true },
  { id: 11, name: 'Mina Girl',  age: 21, bio: 'Live Streamer. Voice/Text mode available.', photo: '/select/girl3.jpg', level: '50,000', location: 'Japan', tags: ['#Live', '#Cute', '#VoiceMode'], intimacy: 25, nextReward: 'Special Video', live: true },
  { id: 1,  name: '瀬戸環奈',  age: 21, bio: 'Fashion Model. Loves Harajuku.', photo: 'https://lh3.googleusercontent.com/u/0/d/1KylTY0pRLLFViFJXcYfp_W4LTK83B8th?q=80&w=800', level: '380,921', location: 'Japan', tags: ['#Fashion', '#J CUP'], intimacy: 85, nextReward: 'Private Photos', live: false },
  { id: 3,  name: '八掛海',    age: 24, bio: 'Photograph. Nature.', photo: 'https://lh3.googleusercontent.com/u/0/d/1uJUrYcs-M6ufcRsakiDtudQkFmhqI7wW?q=80&w=800', level: '380,921', location: 'Japan', tags: ['#Nature', '#野戰'], intimacy: 98, nextReward: 'Virtual Marriage', live: false },
  { id: 4,  name: '小宵こなん', age: 20, bio: 'Art Student. Tea ceremonies.', photo: 'https://lh3.googleusercontent.com/u/0/d/1bGVGNc6z0HRQelZgDGIissDWoqZW_cYh?q=80&w=800', level: '335,964', location: 'Japan', tags: ['#Art', '#Cute'], intimacy: 40, nextReward: 'Video Calls', live: false },
  { id: 5,  name: 'うんぱい',  age: 22, bio: 'Dancer and choreographer.', photo: 'https://upload.wikimedia.org/wikipedia/commons/thumb/7/75/Kindai_Mahjong_Tokonatsu_Festival_%28October_25%2C_2025%29IMG_9861.jpg/250px-Kindai_Mahjong_Tokonatsu_Festival_%28October_25%2C_2025%29IMG_9861.jpg', level: '150,876', location: 'Japan', tags: ['#Dance', '#KPop'], intimacy: 30, nextReward: 'Special Dance', live: false },
  { id: 6,  name: 'Ak野々浦',  age: 20, bio: 'Traditional Japanese artist.', photo: 'https://upload.wikimedia.org/wikipedia/commons/thumb/b/b0/Trend_Girls_Photo_Session_%28May_4%2C_2025%29IMG_0693.jpg/250px-Trend_Girls_Photo_Session_%28May_4%2C_2025%29IMG_0693.jpg', level: '89,420', location: 'Japan', tags: ['#Art', '#Traditional'], intimacy: 25, nextReward: 'Tea Ceremony', live: false },
  { id: 7,  name: '宮島めい',  age: 23, bio: 'Cafe owner, loves indie music.', photo: 'https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/Trend_Girls_Photo_Session_%28September_15%2C_2024%29IMG_9575.jpg/250px-Trend_Girls_Photo_Session_%28September_15%2C_2024%29IMG_9575.jpg', level: '45,000', location: 'Japan', tags: ['#Cafe', '#Music'], intimacy: 20, nextReward: 'Coffee Date', live: false },
  { id: 8,  name: '橋本梨菜',  age: 23, bio: 'Cat Lover, loves indie music.', photo: 'https://lh3.googleusercontent.com/u/0/d/1GlvM9JCNo7FnY6W0-e1vamy21nYciVpC?q=80&w=800', level: '30,000', location: 'Japan', tags: ['#Cat', '#Sleep'], intimacy: 20, nextReward: 'Coffee Date', live: false }
]

const EVENTS = [
  { id: 1, title: 'Global Meet Up',  subtitle: 'Close Touch Your Fantasy!',       dateRange: 'Oct 24 - Nov 21', bannerUrl: 'https://lh3.googleusercontent.com/u/0/d/1V38oc1Ikw9E7S-2gdXVoggyqVfBrmtub', fullImageUrl: 'https://lh3.googleusercontent.com/u/0/d/1z2r2bkdz7B8xgj3g4YFL-D6zn-0wNYX4', description: 'Participate in the Grand Constellation Festival! Collect all 12 limited-edition mini-avatars. Each day offers new challenges and prizes.', participants: 12450 },
  { id: 2, title: 'One on One 2026', subtitle: 'Vote for your favorite performer!', dateRange: 'Nov 01 - Nov 30', bannerUrl: 'https://lh3.googleusercontent.com/u/0/d/1u0ryzh5RNqgQCLJ-gbC3GccAhkuC_cKJ', fullImageUrl: 'https://lh3.googleusercontent.com/u/0/d/1u0ryzh5RNqgQCLJ-gbC3GccAhkuC_cKJ', description: "One on one 2026 is here! Vote for your favorite idols in categories like 'Best Performance,' 'Funniest Content,' and 'Most Charming.'", participants: 9800 },
  { id: 3, title: 'Group Party',     subtitle: 'Most exciting party!!',             dateRange: 'Dec 01 - Dec 25', bannerUrl: 'https://lh3.googleusercontent.com/u/0/d/1Aii1vi_IvZ58rb40kV0_PuIYvM08sOq-', fullImageUrl: 'https://lh3.googleusercontent.com/u/0/d/1Aii1vi_IvZ58rb40kV0_PuIYvM08sOq-', description: 'Celebrate the holidays with our Winter party! Heat up yourself with all your dreaming idols in cold winter.', participants: 7500 }
]

const FRIENDS = [
  { id: 101, name: '瀬戸環奈', status: 'Close Friend', level: 5, avatar: 'https://lh3.googleusercontent.com/u/0/d/1KylTY0pRLLFViFJXcYfp_W4LTK83B8th?q=80&w=400', giftsSent: 50 },
  { id: 102, name: '八掛海',   status: 'VIP Fan',      level: 3, avatar: 'https://lh3.googleusercontent.com/u/0/d/1uJUrYcs-M6ufcRsakiDtudQkFmhqI7wW?q=80&w=400', giftsSent: 120 },
  { id: 103, name: '北岡果林', status: 'Acquaintance', level: 1, avatar: 'https://lh3.googleusercontent.com/u/0/d/1pLeF1znog2_CA0OgdHGe6Gjq2wIgFt9c?q=80&w=400', giftsSent: 5 }
]

// ── State ────────────────────────────────────────────────────────────────────
const activeTab     = ref('home')
const activeFilter  = ref('all')
const searchQuery   = ref('')
const userCoins     = ref(15000)
const selectedAvatar = ref(null)
const selectedEvent  = ref(null)
const showTopUpModal  = ref(false)
const showDailyReward = ref(false)

const tabs = [
  { id: 'home',    icon: '🏠', label: 'Home'    },
  { id: 'events',  icon: '🏆', label: 'Events'  },
  { id: 'friends', icon: '💖', label: 'Friends' },
  { id: 'profile', icon: '👤', label: 'Profile' }
]

const filters = [
  { id: 'all',  label: 'All'      },
  { id: 'live', label: '🔴 Live'  }
]

// ── Computed ─────────────────────────────────────────────────────────────────
const filteredAvatars = computed(() => {
  const q = searchQuery.value.toLowerCase()
  return AVATARS.filter(a => {
    const matchFilter = activeFilter.value === 'all' || (activeFilter.value === 'live' && a.live)
    const matchSearch = !q || a.name.toLowerCase().includes(q) || a.bio.toLowerCase().includes(q) || a.tags.some(t => t.toLowerCase().includes(q))
    return matchFilter && matchSearch
  })
})

const hostIntimacy = computed(() => AVATARS.filter(a => a.intimacy > 10))

// ── Methods ──────────────────────────────────────────────────────────────────
function openAvatar(av) { selectedAvatar.value = av }
function openEvent(ev)  { selectedEvent.value  = ev }

function startChat(av) {
  sessionStorage.setItem('selectedAvatar', JSON.stringify(av))
  selectedAvatar.value = null
  emit('avatar-selected', av)
}

function buyCoins(amount) {
  userCoins.value += amount
  showTopUpModal.value = false
}

function claimDailyReward() {
  userCoins.value += 5000
  showDailyReward.value = false
  sessionStorage.setItem('dailyRewardClaimed', 'true')
}

onMounted(() => {
  if (!sessionStorage.getItem('dailyRewardClaimed')) {
    showDailyReward.value = true
  }
})
</script>

<style scoped>
/* ── Design tokens (match chat UI) ── */
:root {
  --primary: #6366f1;
  --primary-dark: #4f46e5;
  --bg-primary: #0f172a;
  --bg-secondary: #1e293b;
  --bg-tertiary: #334155;
  --text-primary: #f8fafc;
  --text-secondary: #cbd5e1;
  --text-muted: #94a3b8;
  --border: rgba(255,255,255,0.08);
}

/* ── Page shell ── */
.select-page {
  width: 100%;
  height: 100vh;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  color: #f8fafc;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── Header ── */
.select-header {
  flex-shrink: 0;
  z-index: 40;
  background: rgba(15, 23, 42, 0.95);
  backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(255,255,255,0.07);
  box-shadow: 0 4px 24px rgba(0,0,0,0.4);
}
.select-header-inner {
  padding: 0.65rem 1.25rem;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 0.75rem;
  flex-wrap: wrap;
}
/* On mobile: search drops to its own row */
@media (max-width: 540px) {
  .select-header-inner {
    padding: 0.6rem 0.9rem;
  }
  .select-search {
    order: 3;
    flex: 0 0 100%;
    max-width: 100% !important;
    min-width: 0 !important;
  }
}

/* Logo */
.select-logo { display: flex; align-items: center; gap: 0.6rem; flex-shrink: 0; }
.logo-icon {
  width: 40px; height: 40px;
  background: linear-gradient(135deg, #6366f1, #ec4899);
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.2rem; color: white;
  box-shadow: 0 4px 12px rgba(99,102,241,0.4);
}
.logo-text { display: flex; flex-direction: column; }
.logo-main { font-size: 1.25rem; font-weight: 900; color: #f8fafc; letter-spacing: -0.02em; }
.logo-accent { color: #818cf8; }
.logo-ai { font-size: 0.95rem; font-weight: 600; color: #94a3b8; }
.logo-sub { font-size: 0.65rem; color: #64748b; margin-top: -2px; }

/* Search */
.select-search {
  flex: 1; min-width: 160px; max-width: 340px;
  position: relative;
}
.search-icon {
  position: absolute; left: 0.75rem; top: 50%; transform: translateY(-50%);
  color: #64748b; font-size: 0.85rem;
}
.search-input {
  width: 100%;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 999px;
  padding: 0.45rem 0.9rem 0.45rem 2.2rem;
  font-size: 0.85rem; color: #f8fafc;
  outline: none; transition: border-color 0.2s, box-shadow 0.2s;
}
.search-input::placeholder { color: #64748b; }
.search-input:focus {
  border-color: rgba(99,102,241,0.6);
  box-shadow: 0 0 0 3px rgba(99,102,241,0.15);
}

/* Header right */
.select-header-right { display: flex; align-items: center; gap: 0.75rem; flex-shrink: 0; flex-wrap: wrap; }

.coins-btn {
  display: flex; align-items: center; gap: 0.4rem;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(245,158,11,0.3);
  border-radius: 999px;
  padding: 0.4rem 0.9rem;
  cursor: pointer; transition: all 0.2s;
  color: #f8fafc;
}
.coins-btn:hover { background: rgba(245,158,11,0.15); border-color: rgba(245,158,11,0.6); }
.coins-icon { font-size: 0.9rem; }
.coins-value { font-size: 0.85rem; font-weight: 700; }

.filter-chips { display: flex; gap: 0.4rem; }
.filter-chip {
  padding: 0.35rem 0.85rem;
  border-radius: 999px;
  font-size: 0.8rem; font-weight: 600;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.05);
  color: #94a3b8; cursor: pointer; transition: all 0.2s;
}
.filter-chip:hover { background: rgba(255,255,255,0.1); color: #f8fafc; }
.filter-chip.active {
  background: #6366f1; color: white; border-color: #6366f1;
  box-shadow: 0 2px 10px rgba(99,102,241,0.4);
}

/* ── Scrollable body ── */
.select-body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  /* safe-area for notched phones */
  padding-bottom: env(safe-area-inset-bottom, 0);
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,0.15) transparent;
  -webkit-overflow-scrolling: touch;
}
.select-body::-webkit-scrollbar { width: 4px; }
.select-body::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 2px; }

/* ── Bottom Tab Bar ── */
.bottom-tab-bar {
  flex-shrink: 0;
  display: flex;
  background: rgba(15, 23, 42, 0.97);
  backdrop-filter: blur(20px);
  border-top: 1px solid rgba(255,255,255,0.08);
  box-shadow: 0 -4px 24px rgba(0,0,0,0.5);
  /* safe-area padding for home-bar phones */
  padding-bottom: env(safe-area-inset-bottom, 0);
  z-index: 30;
}
.bottom-tab-btn {
  flex: 1;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 0.6rem 0.25rem 0.55rem;
  background: none; border: none; cursor: pointer;
  color: #475569;
  transition: color 0.2s, background 0.2s;
  /* large touch target */
  min-height: 56px;
  -webkit-tap-highlight-color: transparent;
  position: relative;
}
.bottom-tab-btn::before {
  content: '';
  position: absolute; top: 0; left: 50%; transform: translateX(-50%);
  width: 0; height: 2px;
  background: #6366f1;
  border-radius: 0 0 2px 2px;
  transition: width 0.25s;
}
.bottom-tab-btn.active { color: #818cf8; }
.bottom-tab-btn.active::before { width: 32px; }
.bottom-tab-btn:active { background: rgba(255,255,255,0.04); }
.tab-icon { font-size: 1.4rem; line-height: 1; }
.tab-label { font-size: 0.65rem; font-weight: 600; margin-top: 3px; letter-spacing: 0.01em; }

/* ── Section titles ── */
.section-title {
  font-size: 1rem; font-weight: 700; color: #f8fafc;
  padding: 0.85rem 1rem 0.5rem;
}
@media (min-width: 400px) { .section-title { padding: 1rem 1.25rem 0.5rem; } }

/* ── Event banners ── */
.banners-section {
  border-top: 1px solid rgba(255,255,255,0.06);
  padding-bottom: 0.5rem;
}
.banners-scroll {
  display: flex; gap: 0.75rem;
  overflow-x: auto; padding: 0 1.25rem 0.75rem;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
}
.banners-scroll::-webkit-scrollbar { display: none; }
.banner-card {
  position: relative; flex-shrink: 0;
  /* ~80% viewport width on mobile, capped on desktop */
  width: min(80vw, 280px);
  border-radius: 14px; overflow: hidden;
  cursor: pointer; transition: transform 0.2s;
  box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  -webkit-tap-highlight-color: transparent;
}
.banner-card:active { transform: scale(0.97); }
.banner-card:hover { transform: scale(1.02); }
.banner-img { width: 100%; height: 120px; object-fit: cover; display: block; }
.banner-overlay {
  position: absolute; inset: 0;
  background: linear-gradient(to top, rgba(0,0,0,0.78), rgba(0,0,0,0.1));
  display: flex; flex-direction: column; justify-content: flex-end;
  padding: 0.75rem;
}
.banner-title { font-size: 0.9rem; font-weight: 700; color: white; }
.banner-sub { font-size: 0.72rem; color: rgba(255,255,255,0.75); margin-top: 2px; }

/* ── Avatar grid ── */
.avatars-section { padding: 0 0 0.5rem; }
.avatar-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.6rem;
  padding: 0 0.9rem;
}
@media (min-width: 400px)  { .avatar-grid { gap: 0.75rem; padding: 0 1rem; } }
@media (min-width: 480px)  { .avatar-grid { grid-template-columns: repeat(3, 1fr); } }
@media (min-width: 700px)  { .avatar-grid { grid-template-columns: repeat(4, 1fr); padding: 0 1.25rem; } }
@media (min-width: 900px)  { .avatar-grid { grid-template-columns: repeat(5, 1fr); } }
@media (min-width: 1100px) { .avatar-grid { grid-template-columns: repeat(6, 1fr); } }

.avatar-card {
  position: relative; border-radius: 14px; overflow: hidden;
  aspect-ratio: 3/4; cursor: pointer;
  background: #1e293b;
  border: 1px solid rgba(255,255,255,0.07);
  box-shadow: 0 4px 16px rgba(0,0,0,0.35);
  transition: transform 0.25s, box-shadow 0.25s, border-color 0.25s;
  -webkit-tap-highlight-color: transparent;
}
.avatar-card:active { transform: scale(0.97); }
.avatar-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 32px rgba(99,102,241,0.25);
  border-color: rgba(99,102,241,0.5);
}
.avatar-card.is-live { border-color: rgba(239,68,68,0.6); box-shadow: 0 4px 16px rgba(239,68,68,0.2); }
.avatar-card.is-live:hover { box-shadow: 0 12px 32px rgba(239,68,68,0.3); }

.avatar-img-wrap { position: absolute; inset: 0; overflow: hidden; }
.avatar-img { width: 100%; height: 100%; object-fit: cover; object-position: top; transition: transform 0.4s; }
.avatar-card:hover .avatar-img { transform: scale(1.06); }
.avatar-gradient {
  position: absolute; inset: 0;
  background: linear-gradient(to top, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.15) 55%, transparent 100%);
}

.avatar-top-badges {
  position: absolute; top: 0.5rem; left: 0.5rem;
  display: flex; flex-direction: column; gap: 0.3rem;
}
.live-badge {
  display: inline-flex; align-items: center; gap: 0.3rem;
  background: rgba(239,68,68,0.9); color: white;
  font-size: 0.65rem; font-weight: 700;
  padding: 0.2rem 0.5rem; border-radius: 999px;
}
.live-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #fca5a5; flex-shrink: 0;
  animation: livePulse 1.2s ease-out infinite;
  position: relative;
}
.live-dot::before {
  content: ''; position: absolute; inset: 0;
  border-radius: 50%; background: #ef4444;
  animation: livePulse 1.2s ease-out infinite;
}
@keyframes livePulse {
  0%   { transform: scale(1); opacity: 1; }
  100% { transform: scale(2); opacity: 0; }
}
.followers-badge {
  display: inline-block;
  background: rgba(0,0,0,0.55); color: rgba(255,255,255,0.85);
  font-size: 0.65rem; font-weight: 600;
  padding: 0.2rem 0.5rem; border-radius: 999px;
  backdrop-filter: blur(4px);
}

.avatar-bottom {
  position: absolute; bottom: 0; left: 0; right: 0;
  padding: 0.6rem 0.6rem 0.5rem;
}
.avatar-name { font-size: 0.85rem; font-weight: 700; color: white; line-height: 1.2; }
.avatar-tags { display: flex; flex-wrap: wrap; gap: 0.25rem; margin: 0.25rem 0; }
.tag {
  font-size: 0.6rem; font-weight: 600;
  background: rgba(99,102,241,0.7); color: rgba(255,255,255,0.9);
  padding: 0.15rem 0.4rem; border-radius: 4px;
  backdrop-filter: blur(4px);
}
.avatar-loc { font-size: 0.65rem; color: rgba(255,255,255,0.6); margin-top: 0.1rem; }

.avatar-hover-cta {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  opacity: 0;
  background: rgba(99,102,241,0.08);
  transition: opacity 0.25s;
  /* pill styles on the text itself */
  font-size: 0.75rem; font-weight: 700;
  color: #4f46e5;
}
.avatar-hover-cta span {
  background: rgba(255,255,255,0.92);
  color: #4f46e5;
  font-size: 0.75rem; font-weight: 700;
  padding: 0.4rem 1.1rem;
  border-radius: 999px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  transform: translateY(8px);
  transition: transform 0.25s;
  white-space: nowrap;
}
.avatar-card:hover .avatar-hover-cta { opacity: 1; }
.avatar-card:hover .avatar-hover-cta span { transform: translateY(0); }

.empty-state {
  grid-column: 1 / -1; text-align: center; padding: 4rem 1rem;
  color: #64748b;
}
.empty-icon { font-size: 3rem; margin-bottom: 0.75rem; }

/* ── Tab content shared ── */
.tab-content { padding: 0 0.9rem 1rem; }
@media (min-width: 400px) { .tab-content { padding: 0 1.25rem 1rem; } }
.tab-page-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 1rem 0 0.5rem;
  border-bottom: 1px solid rgba(255,255,255,0.07);
  margin-bottom: 0.75rem;
}
.tab-page-header h1 { font-size: 1.3rem; font-weight: 800; color: #818cf8; }
.tab-desc { font-size: 0.85rem; color: #64748b; margin-bottom: 1.25rem; line-height: 1.5; }
.sub-heading { font-size: 1rem; font-weight: 700; color: #f8fafc; margin-bottom: 0.75rem; }
.end-label { text-align: center; color: #475569; font-size: 0.8rem; padding: 1.5rem 0; }

/* ── Events grid ── */
.events-grid { display: grid; grid-template-columns: 1fr; gap: 1rem; }
@media (min-width: 600px) { .events-grid { grid-template-columns: repeat(2, 1fr); } }
@media (min-width: 900px) { .events-grid { grid-template-columns: repeat(3, 1fr); } }

.event-card {
  background: #1e293b; border-radius: 14px; overflow: hidden;
  border: 1px solid rgba(255,255,255,0.07);
  cursor: pointer; transition: transform 0.2s, box-shadow 0.2s;
  box-shadow: 0 4px 16px rgba(0,0,0,0.3);
}
.event-card:hover { transform: translateY(-3px); box-shadow: 0 10px 28px rgba(99,102,241,0.2); }
.event-card-img { width: 100%; height: 160px; object-fit: cover; display: block; }
.event-card-body { padding: 0.9rem; }
.event-card-title { font-size: 1rem; font-weight: 700; color: #f8fafc; }
.event-card-sub { font-size: 0.8rem; color: #818cf8; margin: 0.25rem 0 0.6rem; }
.event-card-footer { display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; color: #64748b; }
.live-now-badge {
  background: #6366f1; color: white;
  font-size: 0.65rem; font-weight: 700;
  padding: 0.2rem 0.6rem; border-radius: 999px;
}

/* ── Friends list ── */
.friends-list { display: flex; flex-direction: column; gap: 0.75rem; }
.friend-card {
  display: flex; align-items: center; gap: 0.9rem;
  background: #1e293b; border-radius: 12px;
  padding: 0.85rem; border: 1px solid rgba(255,255,255,0.07);
  transition: background 0.2s;
}
.friend-card:hover { background: #253347; }
.friend-avatar { width: 52px; height: 52px; border-radius: 50%; object-fit: cover; border: 2px solid #6366f1; flex-shrink: 0; }
.friend-info { flex: 1; }
.friend-info h3 { font-size: 0.9rem; font-weight: 700; color: #f8fafc; }
.friend-info p { font-size: 0.75rem; color: #64748b; margin-top: 2px; }
.friend-gifts { color: #f59e0b !important; }
.friend-chat-btn {
  background: rgba(99,102,241,0.15); border: none; border-radius: 50%;
  width: 36px; height: 36px; cursor: pointer; font-size: 1rem;
  transition: background 0.2s;
}
.friend-chat-btn:hover { background: rgba(99,102,241,0.35); }

/* Intimacy bar */
.intimacy-row { display: flex; justify-content: space-between; font-size: 0.75rem; color: #64748b; margin: 0.25rem 0; }
.intimacy-reward { color: #818cf8; font-weight: 600; }
.intimacy-bar-bg { width: 100%; height: 6px; background: rgba(255,255,255,0.1); border-radius: 999px; overflow: hidden; }
.intimacy-bar-fill { height: 100%; background: linear-gradient(90deg, #6366f1, #ec4899); border-radius: 999px; transition: width 0.6s ease; }

/* ── Profile ── */
.profile-card {
  background: #1e293b; border-radius: 16px;
  padding: 1.5rem; text-align: center;
  border: 1px solid rgba(255,255,255,0.07);
  box-shadow: 0 4px 20px rgba(0,0,0,0.3);
}
.profile-avatar { width: 88px; height: 88px; border-radius: 50%; object-fit: cover; border: 3px solid #6366f1; margin-bottom: 0.75rem; }
.profile-name { font-size: 1.2rem; font-weight: 800; color: #f8fafc; }
.profile-id { font-size: 0.75rem; color: #64748b; margin-top: 0.2rem; }
.profile-badges { display: flex; justify-content: center; gap: 0.5rem; margin: 0.75rem 0; flex-wrap: wrap; }
.profile-badge { font-size: 0.75rem; font-weight: 700; padding: 0.3rem 0.8rem; border-radius: 999px; }
.profile-badge.level { background: rgba(99,102,241,0.2); color: #818cf8; }
.profile-badge.vip   { background: rgba(245,158,11,0.2); color: #f59e0b; }
.profile-stats { display: flex; justify-content: space-around; border-top: 1px solid rgba(255,255,255,0.07); padding-top: 1rem; margin-top: 0.75rem; gap: 0.5rem; }
.stat { display: flex; flex-direction: column; align-items: center; flex: 1; }
.stat-val { font-size: 1rem; font-weight: 800; color: #f8fafc; }
.stat-val.pink { color: #f472b6; }
.stat-val.gold { color: #f59e0b; }
.stat-lbl { font-size: 0.7rem; color: #64748b; margin-top: 2px; }

.settings-list {
  background: #1e293b; border-radius: 12px;
  overflow: hidden; border: 1px solid rgba(255,255,255,0.07);
}
.settings-row {
  width: 100%; display: flex; justify-content: space-between; align-items: center;
  padding: 0.9rem 1rem; background: none; border: none;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  color: #cbd5e1; font-size: 0.9rem; cursor: pointer; text-align: left;
  transition: background 0.15s;
}
.settings-row:last-child { border-bottom: none; }
.settings-row:hover { background: rgba(255,255,255,0.04); }
.settings-icon { margin-right: 0.5rem; }
.settings-arrow { color: #475569; font-size: 1.1rem; }
.signout-btn {
  width: 100%; margin-top: 1rem;
  padding: 0.85rem; border: none; border-radius: 999px;
  background: linear-gradient(135deg, #ef4444, #dc2626);
  color: white; font-size: 0.95rem; font-weight: 700;
  cursor: pointer; transition: opacity 0.2s, transform 0.15s;
  box-shadow: 0 4px 14px rgba(239,68,68,0.35);
}
.signout-btn:hover { opacity: 0.9; transform: translateY(-1px); }

/* ── Modals ── */
.modal-backdrop {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(0,0,0,0.75);
  backdrop-filter: blur(6px);
  display: flex; align-items: flex-end; justify-content: center;
}
@media (min-width: 600px) { .modal-backdrop { align-items: center; } }

/* Avatar modal */
.avatar-modal {
  background: #1e293b;
  width: 100%; max-width: 440px;
  border-radius: 20px 20px 0 0;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,0.1);
  box-shadow: 0 -8px 40px rgba(0,0,0,0.6);
  max-height: 90vh; display: flex; flex-direction: column;
}
@media (min-width: 600px) { .avatar-modal { border-radius: 20px; } }

.avatar-modal-img-wrap { position: relative; flex-shrink: 0; }
.avatar-modal-img { width: 100%; height: 220px; object-fit: cover; object-position: top; display: block; }
.avatar-modal-gradient {
  position: absolute; inset: 0;
  background: linear-gradient(to top, #1e293b 0%, transparent 60%);
}
.modal-close-btn {
  position: absolute; top: 0.75rem; right: 0.75rem;
  width: 32px; height: 32px; border-radius: 50%;
  background: rgba(0,0,0,0.5); border: none;
  color: white; cursor: pointer; font-size: 0.85rem;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.2s;
}
.modal-close-btn:hover { background: rgba(0,0,0,0.75); }
.modal-live-badge {
  position: absolute; top: 0.75rem; left: 0.75rem;
  display: flex; align-items: center; gap: 0.35rem;
  background: rgba(239,68,68,0.9); color: white;
  font-size: 0.75rem; font-weight: 700;
  padding: 0.25rem 0.65rem; border-radius: 999px;
}

.avatar-modal-body { padding: 1.1rem 1.25rem 1.5rem; overflow-y: auto; flex: 1; }
.modal-name-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 0.75rem; margin-bottom: 0.6rem; }
.modal-name { font-size: 1.3rem; font-weight: 900; color: #f8fafc; }
.modal-meta { font-size: 0.8rem; color: #64748b; margin-top: 0.2rem; }
.modal-followers { display: flex; align-items: center; gap: 0.3rem; font-size: 0.85rem; font-weight: 700; color: #f472b6; flex-shrink: 0; }
.modal-bio { font-size: 0.85rem; color: #94a3b8; line-height: 1.55; margin-bottom: 0.9rem; }
.modal-tags { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1rem; }
.modal-tag {
  font-size: 0.75rem; font-weight: 600;
  background: rgba(99,102,241,0.15); color: #818cf8;
  border: 1px solid rgba(99,102,241,0.3);
  padding: 0.3rem 0.7rem; border-radius: 999px;
}
.modal-intimacy { margin-bottom: 1.25rem; }
.intimacy-label-row { display: flex; justify-content: space-between; font-size: 0.78rem; color: #64748b; margin-bottom: 0.4rem; }
.intimacy-pct { color: #818cf8; font-weight: 600; }
.intimacy-next { font-size: 0.75rem; color: #64748b; margin-top: 0.4rem; }

.start-chat-btn {
  width: 100%; padding: 0.9rem; border: none; border-radius: 14px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white; font-size: 1rem; font-weight: 700;
  cursor: pointer; transition: opacity 0.2s, transform 0.15s;
  box-shadow: 0 4px 16px rgba(99,102,241,0.4);
}
.start-chat-btn:hover { opacity: 0.9; transform: translateY(-1px); }
.start-chat-btn.is-live {
  background: linear-gradient(135deg, #ef4444, #ec4899);
  box-shadow: 0 4px 16px rgba(239,68,68,0.4);
}

/* Event modal */
.event-modal {
  background: #1e293b;
  width: 100%; max-width: 600px;
  border-radius: 20px 20px 0 0;
  padding: 1.25rem;
  overflow-y: auto; max-height: 90vh;
  border: 1px solid rgba(255,255,255,0.1);
  box-shadow: 0 -8px 40px rgba(0,0,0,0.6);
}
@media (min-width: 600px) { .event-modal { border-radius: 20px; } }
.event-modal-header { display: flex; justify-content: flex-end; margin-bottom: 0.75rem; }
.modal-close-btn-inline { background: none; border: none; font-size: 1.2rem; cursor: pointer; color: #64748b; transition: color 0.2s; }
.modal-close-btn-inline:hover { color: #f8fafc; }
.event-modal-img { width: 100%; border-radius: 12px; object-fit: cover; margin-bottom: 1rem; box-shadow: 0 4px 16px rgba(0,0,0,0.4); }
.event-modal-title { font-size: 1.4rem; font-weight: 900; color: #f8fafc; margin-bottom: 0.25rem; }
.event-modal-sub { color: #818cf8; font-weight: 600; font-size: 0.9rem; margin-bottom: 0.9rem; }
.event-modal-meta {
  display: flex; justify-content: space-between;
  background: rgba(255,255,255,0.05); border-radius: 10px;
  padding: 0.7rem 1rem; font-size: 0.8rem; color: #94a3b8;
  margin-bottom: 0.9rem;
}
.event-modal-desc { font-size: 0.85rem; color: #94a3b8; line-height: 1.6; margin-bottom: 1.25rem; }
.join-btn {
  width: 100%; padding: 0.85rem; border: none; border-radius: 999px;
  background: linear-gradient(135deg, #6366f1, #ec4899);
  color: white; font-size: 0.95rem; font-weight: 700;
  cursor: pointer; transition: opacity 0.2s;
  box-shadow: 0 4px 14px rgba(99,102,241,0.4);
}
.join-btn:hover { opacity: 0.9; }

/* Top-up modal */
.topup-modal {
  background: #1e293b;
  width: 100%; max-width: 400px;
  border-radius: 20px 20px 0 0;
  padding: 1.5rem;
  border: 1px solid rgba(255,255,255,0.1);
  box-shadow: 0 -8px 40px rgba(0,0,0,0.6);
}
@media (min-width: 600px) { .topup-modal { border-radius: 20px; } }
.topup-title { font-size: 1.3rem; font-weight: 800; color: #818cf8; text-align: center; margin-bottom: 1.25rem; }
.topup-options { display: flex; flex-direction: column; gap: 0.75rem; margin-bottom: 1rem; }
.topup-option {
  position: relative; display: flex; justify-content: space-between; align-items: center;
  background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
  border-radius: 12px; padding: 0.9rem 1rem;
  cursor: pointer; transition: all 0.2s;
}
.topup-option:hover { background: rgba(99,102,241,0.15); border-color: rgba(99,102,241,0.4); }
.topup-option.best { border-color: rgba(245,158,11,0.4); }
.topup-option.best:hover { background: rgba(245,158,11,0.1); }
.topup-best-tag {
  position: absolute; top: -10px; right: 10px;
  background: #f59e0b; color: #000; font-size: 0.65rem; font-weight: 700;
  padding: 0.15rem 0.5rem; border-radius: 999px;
}
.topup-amount { font-size: 0.95rem; font-weight: 700; color: #f8fafc; }
.topup-price { font-size: 0.95rem; font-weight: 800; color: #818cf8; }
.topup-cancel {
  width: 100%; padding: 0.75rem; border: none; border-radius: 999px;
  background: rgba(255,255,255,0.08); color: #94a3b8;
  font-size: 0.9rem; font-weight: 600; cursor: pointer; transition: background 0.2s;
}
.topup-cancel:hover { background: rgba(255,255,255,0.14); }

/* Daily reward modal */
.daily-modal {
  background: #1e293b;
  width: 100%; max-width: 380px;
  border-radius: 20px 20px 0 0;
  padding: 2rem 1.5rem;
  text-align: center;
  border: 2px solid rgba(245,158,11,0.5);
  box-shadow: 0 -8px 40px rgba(0,0,0,0.6);
}
@media (min-width: 600px) { .daily-modal { border-radius: 20px; } }
.daily-title { font-size: 1.4rem; font-weight: 900; color: #818cf8; margin-bottom: 0.25rem; }
.daily-streak { font-size: 0.85rem; color: #64748b; margin-bottom: 1rem; }
.daily-gift { font-size: 4rem; margin-bottom: 1rem; animation: bounce 1s infinite; }
@keyframes bounce { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-10px); } }
.daily-reward-box {
  background: rgba(245,158,11,0.1); border: 2px solid rgba(245,158,11,0.4);
  border-radius: 12px; padding: 0.85rem; font-size: 1.1rem; font-weight: 900;
  color: #f8fafc; margin-bottom: 1.5rem;
}
.daily-claim-btn {
  width: 100%; padding: 0.9rem; border: none; border-radius: 999px;
  background: linear-gradient(135deg, #6366f1, #ec4899);
  color: white; font-size: 1rem; font-weight: 700;
  cursor: pointer; transition: opacity 0.2s;
  box-shadow: 0 4px 14px rgba(99,102,241,0.4);
}
.daily-claim-btn:hover { opacity: 0.9; }

/* ── Modal transition ── */
.modal-enter-active, .modal-leave-active { transition: opacity 0.2s; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
.modal-enter-active .avatar-modal,
.modal-enter-active .event-modal,
.modal-enter-active .topup-modal,
.modal-enter-active .daily-modal {
  transition: transform 0.25s ease;
}
.modal-enter-from .avatar-modal,
.modal-enter-from .event-modal,
.modal-enter-from .topup-modal,
.modal-enter-from .daily-modal {
  transform: translateY(40px);
}
</style>
