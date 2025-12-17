import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

// Import Global Styles
import './assets/css/reset.css'
import './assets/css/variables.css'
import './assets/css/base.css'
import '@phosphor-icons/web/regular'; // Load Phosphor Icons

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
