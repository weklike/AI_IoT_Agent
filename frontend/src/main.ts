import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import DeviceList from './pages/DeviceList.vue'
import DeviceDetail from './pages/DeviceDetail.vue'
import AgentChat from './pages/AgentChat.vue'
import './style.css'
const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/', redirect: '/devices' }, { path: '/devices', component: DeviceList },
  { path: '/devices/:id', component: DeviceDetail }, { path: '/agent', component: AgentChat }
] })
createApp(App).use(router).mount('#app')
