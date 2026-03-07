import { mount } from 'svelte';
import '@civicos/components/src/theme/index.css';
import { initTheme } from '@civicos/components';
import Options from './Options.svelte';

initTheme();

const app = mount(Options, { target: document.getElementById('app')! });

export default app;
