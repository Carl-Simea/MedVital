import type { ModuleId } from './observation'

export interface ModuleDescriptor {
  id: ModuleId
  name: string
  description: string
}

/**
 * Static shell metadata so the app can render offline before the API has ever been
 * reached. Metric definitions come from GET /api/v1/modules (backend is authoritative).
 */
export const MODULES: readonly ModuleDescriptor[] = [
  { id: 'radiation', name: 'Radiation', description: 'Accumulated absorbed dose and dose equivalent.' },
  { id: 'bone', name: 'Bone health', description: 'Bone mineral density change and trend per site.' },
  {
    id: 'cardiovascular',
    name: 'Cardiovascular health',
    description: 'Heart rate, blood pressure and heart-rate variability.',
  },
  {
    id: 'behavioral',
    name: 'Behavioral health',
    description: 'Sleep and self-report series relative to each subject’s own baseline.',
  },
]
