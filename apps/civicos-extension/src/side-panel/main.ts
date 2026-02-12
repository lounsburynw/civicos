import { mount } from 'svelte';
import SidePanel from './SidePanel.svelte';

const app = mount(SidePanel, { target: document.getElementById('app')! });

export default app;
