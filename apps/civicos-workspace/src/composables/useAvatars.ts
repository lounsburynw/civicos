/**
 * Avatar generation composable using DiceBear API
 *
 * Uses DiceBear's free API to generate consistent, deterministic avatars
 * based on user IDs. No backend storage or authentication required.
 *
 * API: https://api.dicebear.com/7.x/{style}/svg
 * Style: shapes (geometric shapes - race/gender neutral, friendly, colorful)
 */

export function useAvatars() {
  /**
   * Generate avatar URL for a user
   *
   * @param userId - User identifier (e.g., "demo_user", "user_123")
   * @param size - Avatar size in pixels (default: 40)
   * @returns URL to DiceBear SVG avatar
   *
   * @example
   * const { getAvatarUrl } = useAvatars()
   * const avatarUrl = getAvatarUrl('demo_user', 40)
   * // Returns: https://api.dicebear.com/7.x/shapes/svg?seed=demo_user&size=40
   */
  const getAvatarUrl = (userId: string, size: number = 40): string => {
    // Encode userId to handle special characters
    const seed = encodeURIComponent(userId);

    // Use "shapes" style for race/gender neutral geometric avatars
    // Clean, modern, colorful abstract shapes - friendly and approachable
    return `https://api.dicebear.com/7.x/shapes/svg?seed=${seed}&size=${size}`;
  };

  return {
    getAvatarUrl
  };
}
