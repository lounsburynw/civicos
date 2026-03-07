import { mount } from 'svelte';
import '@civicos/components/src/theme/index.css';
import { initTheme } from '@civicos/components';
import Popup from './Popup.svelte';

initTheme();

const app = mount(Popup, { target: document.getElementById('app')! });

export default app;
