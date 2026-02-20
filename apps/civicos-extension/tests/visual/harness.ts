import { mount } from 'svelte';
import HarnessApp from './HarnessApp.svelte';

const params = new URLSearchParams(window.location.search);
const level = params.get('level') || 'city';

mount(HarnessApp, {
  target: document.getElementById('app')!,
  props: { level },
});
