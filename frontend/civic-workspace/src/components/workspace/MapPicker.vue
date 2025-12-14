<template>
  <div class="map-picker">
    <!-- Search Box Overlay -->
    <div class="search-controls">
      <input
        ref="searchInput"
        type="text"
        class="search-input"
        placeholder="Search for an address..."
      />
      <button
        @click="getUserLocation"
        class="location-btn"
        type="button"
        title="Use my current location"
        :disabled="isGettingLocation"
      >
        <span v-if="isGettingLocation" class="spinner">⏳</span>
        <span v-else class="icon">📍</span>
        {{ isGettingLocation ? 'Getting location...' : 'My Location' }}
      </button>
    </div>

    <!-- Map Container -->
    <div ref="mapContainer" class="map-container" :style="{ height: mapHeight }"></div>

    <!-- Location Info Overlay -->
    <div v-if="currentAddress || (lat !== null && lng !== null)" class="location-info">
      <div class="location-address">
        <span class="icon">📍</span>
        <span v-if="currentAddress" class="address-text">{{ currentAddress }}</span>
        <span v-else class="coords-text">{{ lat?.toFixed(6) }}, {{ lng?.toFixed(6) }}</span>
      </div>
      <button
        v-if="currentAddress || (lat !== null && lng !== null)"
        @click="clearLocation"
        class="clear-btn"
        type="button"
        title="Clear location"
      >
        Clear
      </button>
    </div>

    <!-- Instructions -->
    <div class="map-instructions">
      <span class="icon">💡</span>
      <span>Search, click, or drag the pin to select a location</span>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="map-loading">
      <span class="spinner">⏳</span>
      Loading map...
    </div>

    <!-- Error State -->
    <div v-if="error" class="map-error">
      <span class="icon">⚠️</span>
      {{ error }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { api } from '@/services/api'
import { useUserStore } from '@/stores/user'

interface Props {
  modelValue?: {
    address: string
    lat: number | null
    lng: number | null
  }
  mapHeight?: string
  initialCenter?: { lat: number; lng: number }
  initialZoom?: number
}

const props = withDefaults(defineProps<Props>(), {
  mapHeight: '400px',
  initialZoom: 14
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: { address: string; lat: number | null; lng: number | null }): void
}>()

const userStore = useUserStore()
const mapContainer = ref<HTMLDivElement | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)
const isLoading = ref(true)
const isGettingLocation = ref(false)
const error = ref('')

const lat = ref<number | null>(props.modelValue?.lat || null)
const lng = ref<number | null>(props.modelValue?.lng || null)
const currentAddress = ref(props.modelValue?.address || '')

let map: google.maps.Map | null = null
let marker: google.maps.Marker | null = null
let geocoder: google.maps.Geocoder | null = null
let autocomplete: google.maps.places.Autocomplete | null = null

// Track if Google Maps script is loaded
let googleMapsLoaded = false
let googleMapsLoading = false
let googleMapsLoadPromise: Promise<void> | null = null

/**
 * Load Google Maps JavaScript API
 */
async function loadGoogleMaps(): Promise<void> {
  // If already loaded, return immediately
  if (googleMapsLoaded || (window as any).google?.maps) {
    googleMapsLoaded = true
    return Promise.resolve()
  }

  // If currently loading, return the existing promise
  if (googleMapsLoading && googleMapsLoadPromise) {
    return googleMapsLoadPromise
  }

  // Start loading
  googleMapsLoading = true
  googleMapsLoadPromise = new Promise(async (resolve, reject) => {
    try {
      // Get API key from backend
      const apiKey = await api.getGoogleMapsApiKey()

      if (!apiKey) {
        throw new Error('Google Maps API key not configured')
      }

      console.log('[MapPicker] Loading Google Maps API...')

      // Load Google Maps script
      const script = document.createElement('script')
      script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places&callback=initGoogleMapsForPicker`
      script.async = true
      script.defer = true

      // Set up global callback
      ;(window as any).initGoogleMapsForPicker = () => {
        googleMapsLoaded = true
        googleMapsLoading = false
        console.log('[MapPicker] Google Maps API loaded successfully')
        resolve()
      }

      script.onerror = () => {
        googleMapsLoading = false
        reject(new Error('Failed to load Google Maps script'))
      }

      document.head.appendChild(script)
    } catch (error) {
      googleMapsLoading = false
      console.error('[MapPicker] Error loading Google Maps:', error)
      reject(error)
    }
  })

  return googleMapsLoadPromise
}

/**
 * Initialize the map
 */
async function initMap() {
  if (!mapContainer.value) {
    console.error('[MapPicker] Map container not available')
    return
  }

  try {
    isLoading.value = true
    error.value = ''

    // Load Google Maps API
    await loadGoogleMaps()

    if (!window.google || !window.google.maps) {
      throw new Error('Google Maps API not loaded')
    }

    // Determine initial center
    let center = props.initialCenter
    if (!center && userStore.cityName) {
      // Try to geocode user's city for better initial positioning
      center = await geocodeCity(userStore.cityName)
    }
    if (!center) {
      // Default to San Francisco Bay Area
      center = { lat: 37.8715, lng: -122.2730 }
    }

    // Create map
    map = new google.maps.Map(mapContainer.value, {
      center,
      zoom: props.initialZoom,
      mapTypeControl: true,
      streetViewControl: true,
      fullscreenControl: false,
      zoomControl: true,
      gestureHandling: 'greedy'
    })

    // Create geocoder for reverse geocoding
    geocoder = new google.maps.Geocoder()

    // Create draggable marker
    marker = new google.maps.Marker({
      map,
      position: lat.value && lng.value ? { lat: lat.value, lng: lng.value } : center,
      draggable: true,
      title: 'Drag to select location',
      animation: google.maps.Animation.DROP
    })

    // If we have initial lat/lng, update the position
    if (lat.value && lng.value) {
      const position = { lat: lat.value, lng: lng.value }
      marker.setPosition(position)
      map.setCenter(position)
    }

    // Listen for marker drag
    marker.addListener('dragend', async () => {
      const position = marker!.getPosition()
      if (position) {
        await updateLocation(position.lat(), position.lng())
      }
    })

    // Listen for map clicks to move marker
    map.addListener('click', async (e: google.maps.MapMouseEvent) => {
      if (e.latLng) {
        marker!.setPosition(e.latLng)
        await updateLocation(e.latLng.lat(), e.latLng.lng())
      }
    })

    // Setup Places Autocomplete for search input
    if (searchInput.value) {
      autocomplete = new google.maps.places.Autocomplete(searchInput.value, {
        fields: ['formatted_address', 'geometry', 'name'],
        types: ['address']
      })

      // Bias results to map viewport
      autocomplete.bindTo('bounds', map)

      // Listen for place selection
      autocomplete.addListener('place_changed', () => {
        const place = autocomplete!.getPlace()

        if (!place.geometry || !place.geometry.location) {
          console.warn('[MapPicker] No location found for selected place')
          return
        }

        // Move marker and map to selected location
        const location = place.geometry.location
        marker!.setPosition(location)
        map!.setCenter(location)
        map!.setZoom(17) // Zoom in closer for address

        // Update location
        updateLocation(location.lat(), location.lng())

        // Clear search input
        if (searchInput.value) {
          searchInput.value.value = ''
        }
      })
    }

    // Try to get user's location on load (optional, non-blocking)
    tryAutoLocate()

    isLoading.value = false
    console.log('[MapPicker] Map initialized')
  } catch (err: any) {
    console.error('[MapPicker] Failed to initialize map:', err)
    error.value = 'Failed to load map. Please try again.'
    isLoading.value = false
  }
}

/**
 * Geocode city name to get coordinates
 */
async function geocodeCity(cityName: string): Promise<{ lat: number; lng: number } | undefined> {
  try {
    const geocoder = new google.maps.Geocoder()
    const result = await geocoder.geocode({ address: cityName })

    if (result.results && result.results.length > 0) {
      const location = result.results[0].geometry.location
      return { lat: location.lat(), lng: location.lng() }
    }
  } catch (err) {
    console.warn('[MapPicker] Failed to geocode city:', err)
  }
  return undefined
}

/**
 * Update location when pin is moved
 */
async function updateLocation(newLat: number, newLng: number) {
  lat.value = newLat
  lng.value = newLng

  // Reverse geocode to get address
  if (geocoder) {
    try {
      const result = await geocoder.geocode({ location: { lat: newLat, lng: newLng } })

      if (result.results && result.results.length > 0) {
        currentAddress.value = result.results[0].formatted_address
      } else {
        currentAddress.value = ''
      }
    } catch (err) {
      console.warn('[MapPicker] Reverse geocoding failed:', err)
      currentAddress.value = ''
    }
  }

  // Emit update
  emit('update:modelValue', {
    address: currentAddress.value,
    lat: lat.value,
    lng: lng.value
  })

  console.log('[MapPicker] Location updated:', {
    address: currentAddress.value,
    lat: lat.value,
    lng: lng.value
  })
}

/**
 * Clear the current location
 */
function clearLocation() {
  lat.value = null
  lng.value = null
  currentAddress.value = ''

  // Reset marker to center
  if (map && marker) {
    const center = map.getCenter()
    if (center) {
      marker.setPosition(center)
    }
  }

  emit('update:modelValue', {
    address: '',
    lat: null,
    lng: null
  })
}

/**
 * Get user's current location using Geolocation API
 */
async function getUserLocation() {
  if (!navigator.geolocation) {
    alert('Geolocation is not supported by your browser')
    return
  }

  isGettingLocation.value = true

  try {
    const position = await new Promise<GeolocationPosition>((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0
      })
    })

    const { latitude, longitude } = position.coords

    // Move marker and map to user's location
    if (marker && map) {
      const location = { lat: latitude, lng: longitude }
      marker.setPosition(location)
      map.setCenter(location)
      map.setZoom(17) // Zoom in closer

      // Update location
      await updateLocation(latitude, longitude)
    }

    console.log('[MapPicker] User location obtained:', { latitude, longitude })
  } catch (err: any) {
    console.warn('[MapPicker] Failed to get user location:', err)

    if (err.code === 1) {
      alert('Location access denied. Please enable location permissions in your browser.')
    } else if (err.code === 2) {
      alert('Location unavailable. Please try again.')
    } else if (err.code === 3) {
      alert('Location request timed out. Please try again.')
    } else {
      alert('Failed to get your location. Please try again.')
    }
  } finally {
    isGettingLocation.value = false
  }
}

/**
 * Try to automatically locate user on map load (non-blocking, silent failure)
 */
async function tryAutoLocate() {
  if (!navigator.geolocation || lat.value !== null) {
    // Don't auto-locate if geolocation unavailable or location already set
    return
  }

  try {
    const position = await new Promise<GeolocationPosition>((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: false, // Lower accuracy for faster response
        timeout: 5000,
        maximumAge: 300000 // Accept 5-minute-old cached position
      })
    })

    const { latitude, longitude } = position.coords

    // Only auto-center if user hasn't set a location yet
    if (marker && map && lat.value === null) {
      const location = { lat: latitude, lng: longitude }
      marker.setPosition(location)
      map.setCenter(location)
      console.log('[MapPicker] Auto-located user:', { latitude, longitude })
    }
  } catch (err) {
    // Silent failure - user can still manually set location
    console.log('[MapPicker] Auto-locate skipped (user can enable manually)')
  }
}

// Watch for external changes to modelValue
watch(() => props.modelValue, (newValue) => {
  if (newValue && newValue.lat !== null && newValue.lng !== null) {
    lat.value = newValue.lat
    lng.value = newValue.lng
    currentAddress.value = newValue.address

    // Update marker position if map is loaded
    if (marker) {
      const position = { lat: newValue.lat, lng: newValue.lng }
      marker.setPosition(position)
      map?.setCenter(position)
    }
  }
}, { deep: true })

onMounted(() => {
  initMap()
})

onUnmounted(() => {
  // Cleanup map
  if (marker) {
    marker.setMap(null)
    marker = null
  }
  if (map) {
    map = null
  }
})
</script>

<style scoped>
.map-picker {
  position: relative;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--background-secondary);
}

/* Search Controls Overlay */
.search-controls {
  position: absolute;
  top: var(--space-sm);
  left: var(--space-sm);
  right: var(--space-sm);
  display: flex;
  gap: var(--space-sm);
  z-index: 10;
}

.search-input {
  flex: 1;
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: white;
  color: var(--text-primary);
  font-size: var(--font-size-base);
  font-family: var(--font-family);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  transition: all var(--transition-fast);
}

.search-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 2px 12px rgba(38, 139, 210, 0.3);
}

.search-input::placeholder {
  color: var(--text-secondary);
  opacity: 0.7;
}

.location-btn {
  padding: var(--space-sm) var(--space-md);
  background: white;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.location-btn:hover:not(:disabled) {
  background: var(--hover-bg);
  border-color: var(--primary);
  color: var(--primary);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.location-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.location-btn .icon {
  font-size: 14px;
}

.map-container {
  width: 100%;
  background: var(--background-extra-light);
}

.location-info {
  position: absolute;
  top: calc(var(--space-sm) + 48px); /* Below search controls */
  left: var(--space-sm);
  right: var(--space-sm);
  background: white;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: var(--space-sm) var(--space-md);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
  z-index: 10;
}

.location-address {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  flex: 1;
  min-width: 0;
}

.address-text,
.coords-text {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.coords-text {
  font-family: monospace;
  color: var(--text-secondary);
}

.clear-btn {
  padding: var(--space-xs) var(--space-sm);
  background: var(--background-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.clear-btn:hover {
  background: var(--hover-bg);
  color: var(--accent-red);
  border-color: var(--accent-red);
}

.map-instructions {
  position: absolute;
  bottom: var(--space-sm);
  left: 50%;
  transform: translateX(-50%);
  background: white;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: var(--space-xs) var(--space-md);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  z-index: 10;
  pointer-events: none;
}

.map-loading,
.map-error {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: white;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-md) var(--space-lg);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: var(--font-size-base);
  z-index: 20;
}

.map-loading {
  color: var(--text-secondary);
}

.map-error {
  color: var(--accent-red);
  border-color: var(--accent-red);
}

.spinner {
  display: inline-block;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.icon {
  font-style: normal;
  font-size: 16px;
}
</style>
