/**
 * Composable for Google Places Autocomplete
 *
 * Provides reactive Google Places Autocomplete functionality for address input fields.
 * Loads Google Maps JavaScript API dynamically and manages autocomplete instance.
 *
 * Usage:
 * ```typescript
 * const { initAutocomplete, address, lat, lng, isReady } = useGooglePlaces()
 *
 * onMounted(() => {
 *   initAutocomplete(inputRef.value, {
 *     bounds: boundsObject,  // Optional: restrict to specific area
 *     componentRestrictions: { country: 'us' }
 *   })
 * })
 * ```
 */

import { ref, onUnmounted } from 'vue'
import { api } from '@/services/api'

// Track if Google Maps script is loaded
let googleMapsLoaded = false
let googleMapsLoading = false
let googleMapsLoadPromise: Promise<void> | null = null

interface PlaceResult {
  address: string
  lat: number
  lng: number
  formattedAddress: string
}

interface AutocompleteOptions {
  bounds?: google.maps.LatLngBounds
  componentRestrictions?: google.maps.places.ComponentRestrictions
  types?: string[]
}

export function useGooglePlaces() {
  const isReady = ref(false)
  const address = ref('')
  const lat = ref<number | null>(null)
  const lng = ref<number | null>(null)
  const formattedAddress = ref('')

  let autocomplete: google.maps.places.Autocomplete | null = null

  /**
   * Load Google Maps JavaScript API
   */
  async function loadGoogleMaps(): Promise<void> {
    // If already loaded, return immediately
    if (googleMapsLoaded) {
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
        const response = await fetch(`${api['baseURL']}/api/config/google-maps-key`)
        const data = await response.json()
        const apiKey = data.api_key

        if (!apiKey) {
          throw new Error('Google Maps API key not configured')
        }

        // Load Google Maps script
        const script = document.createElement('script')
        script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places&callback=initGoogleMaps`
        script.async = true
        script.defer = true

        // Set up global callback
        ;(window as any).initGoogleMaps = () => {
          googleMapsLoaded = true
          googleMapsLoading = false
          console.log('[useGooglePlaces] Google Maps API loaded')
          resolve()
        }

        script.onerror = () => {
          googleMapsLoading = false
          reject(new Error('Failed to load Google Maps script'))
        }

        document.head.appendChild(script)
      } catch (error) {
        googleMapsLoading = false
        reject(error)
      }
    })

    return googleMapsLoadPromise
  }

  /**
   * Initialize autocomplete on an input element
   */
  async function initAutocomplete(
    inputElement: HTMLInputElement | null,
    options: AutocompleteOptions = {}
  ): Promise<void> {
    if (!inputElement) {
      console.warn('[useGooglePlaces] Input element not provided')
      return
    }

    try {
      // Load Google Maps API if not already loaded
      await loadGoogleMaps()

      // Create autocomplete instance
      const autocompleteOptions: google.maps.places.AutocompleteOptions = {
        fields: ['formatted_address', 'geometry', 'address_components'],
        ...options
      }

      autocomplete = new google.maps.places.Autocomplete(
        inputElement,
        autocompleteOptions
      )

      // Listen for place selection
      autocomplete.addListener('place_changed', () => {
        const place = autocomplete!.getPlace()

        if (!place.geometry || !place.geometry.location) {
          console.warn('[useGooglePlaces] No geometry for selected place')
          return
        }

        // Extract data
        const location = place.geometry.location
        address.value = inputElement.value
        lat.value = location.lat()
        lng.value = location.lng()
        formattedAddress.value = place.formatted_address || ''

        console.log('[useGooglePlaces] Place selected:', {
          address: address.value,
          lat: lat.value,
          lng: lng.value
        })
      })

      isReady.value = true
      console.log('[useGooglePlaces] Autocomplete initialized')
    } catch (error) {
      console.error('[useGooglePlaces] Failed to initialize autocomplete:', error)
      throw error
    }
  }

  /**
   * Clear the current place data
   */
  function clearPlace() {
    address.value = ''
    lat.value = null
    lng.value = null
    formattedAddress.value = ''
  }

  /**
   * Cleanup on component unmount
   */
  onUnmounted(() => {
    if (autocomplete) {
      google.maps.event.clearInstanceListeners(autocomplete)
      autocomplete = null
    }
  })

  return {
    // State
    isReady,
    address,
    lat,
    lng,
    formattedAddress,

    // Methods
    initAutocomplete,
    clearPlace
  }
}
