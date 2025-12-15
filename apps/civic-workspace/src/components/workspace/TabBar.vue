<script setup lang="ts">
import { computed } from 'vue'
import { Calendar, FileText, Landmark, AlertCircle, MessageSquare } from 'lucide-vue-next'
import { useWorkspaceStore } from '../../stores/workspace'
import type { Component } from 'vue'

const workspace = useWorkspaceStore()

const tabs = computed(() => workspace.openArtifacts)
const activeIndex = computed(() => workspace.activeArtifactIndex)

function handleTabClick(index: number) {
  workspace.setActiveArtifact(index)
}

function handleCloseTab(index: number, event: Event) {
  event.stopPropagation() // Prevent tab selection when closing
  workspace.closeArtifact(index)
}

function getTabIcon(tab: any): Component {
  switch (tab.type) {
    case 'event':
      return Calendar
    case 'bill':
      return FileText
    case 'program':
      return Landmark
    case 'thread':
      // All threads use MessageSquare (discussion icon) regardless of focal_type
      return MessageSquare
    case 'issue':
      // Issue artifact uses AlertCircle
      return AlertCircle
    default:
      return FileText
  }
}

function truncateTitle(title: string, maxLength: number = 30): string {
  if (title.length <= maxLength) return title
  return title.slice(0, maxLength - 3) + '...'
}
</script>

<template>
  <div class="tab-bar" v-if="tabs.length > 0">
    <div class="tab-scroll-container">
      <div
        v-for="(tab, index) in tabs"
        :key="tab.id"
        class="tab"
        :class="{ 'tab--active': index === activeIndex }"
        @click="handleTabClick(index)"
        :title="tab.title"
      >
        <component :is="getTabIcon(tab)" :size="14" class="tab__icon" />
        <span class="tab__title">{{ truncateTitle(tab.title) }}</span>
        <button
          class="tab__close"
          @click="handleCloseTab(index, $event)"
          aria-label="Close tab"
        >
          ×
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tab-bar {
  display: flex;
  align-items: center;
  height: 40px;
  background: var(--solarized-base3);
  border-bottom: 1px solid var(--solarized-base2);
  overflow: hidden;
}

.tab-scroll-container {
  display: flex;
  align-items: center;
  height: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  flex: 1;
  gap: 2px;
  padding: 0 4px;
}

/* Hide scrollbar but keep functionality */
.tab-scroll-container::-webkit-scrollbar {
  height: 4px;
}

.tab-scroll-container::-webkit-scrollbar-track {
  background: transparent;
}

.tab-scroll-container::-webkit-scrollbar-thumb {
  background: var(--solarized-base2);
  border-radius: 2px;
}

.tab-scroll-container::-webkit-scrollbar-thumb:hover {
  background: var(--solarized-base1);
}

.tab {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 30px;
  padding: 0 16px;
  background: rgba(0, 0, 0, 0.08);
  border: 1px solid var(--solarized-base1);
  border-bottom: none;
  border-radius: 8px 8px 0 0;
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;
  min-width: 120px;
  max-width: 250px;
  user-select: none;
  position: relative;
  margin-right: 2px;
  opacity: 0.7;
}

.tab:hover {
  background: rgba(0, 0, 0, 0.05);
  opacity: 0.85;
  transform: translateY(-1px);
}

.tab--active {
  background: var(--solarized-base3);
  border: 1px solid var(--solarized-base1);
  border-bottom-color: transparent;
  border-top: 3px solid var(--solarized-blue);
  margin-bottom: -1px;
  height: 37px;
  opacity: 1;
  z-index: 10;
  box-shadow:
    0 -3px 8px rgba(0, 0, 0, 0.12),
    2px 0 6px rgba(0, 0, 0, 0.06),
    -2px 0 6px rgba(0, 0, 0, 0.06);
}

.tab--active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--solarized-base3);
  z-index: 11;
}

.tab__icon {
  flex-shrink: 0;
  color: var(--solarized-base01);
}

.tab--active .tab__icon {
  color: var(--solarized-base02);
}

.tab__title {
  flex: 1;
  font-size: 13px;
  color: var(--solarized-base01);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tab--active .tab__title {
  color: var(--solarized-base02);
  font-weight: 500;
}

.tab__close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 3px;
  color: var(--solarized-base1);
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;
}

.tab__close:hover {
  background: var(--solarized-base2);
  color: var(--solarized-base02);
}

.tab--active .tab__close:hover {
  background: var(--solarized-base2);
  color: var(--solarized-base02);
}
</style>
