import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

// Import Global Styles
import './assets/css/reset.css'
import './assets/css/variables.css'
import './assets/css/base.css'
import '@phosphor-icons/web/regular'; // Load Phosphor Icons

// Note: window.__API_BASE__ is set dynamically in index.html based on environment
// Do not override it here to allow proper environment detection

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
