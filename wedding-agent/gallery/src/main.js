import { mountPortal } from '@web/portalMain.js'
import './gallery.css'
import App from './App.vue'
import { portal } from './api.js'

mountPortal(App, portal, 'COBLANC · GALLERY')
