import { mount } from 'svelte';
import '@civicos/components/src/theme/index.css';
import { initTheme } from '@civicos/components';
import SidePanel from './SidePanel.svelte';

initTheme();

const app = mount(SidePanel, { target: document.getElementById('app')! });

export default app;
