import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'
import { appearance } from './lib/appearance.svelte'

appearance.apply()

const app = mount(App, {
  target: document.getElementById('app')!,
})

export default app
