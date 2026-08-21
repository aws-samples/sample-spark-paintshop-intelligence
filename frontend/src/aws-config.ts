import type { AppConfig } from './types'

let _config: AppConfig | null = null

export async function loadConfig(): Promise<AppConfig> {
  if (_config) return _config
  const resp = await fetch('/config.json')
  if (!resp.ok) throw new Error('Failed to load /config.json')
  _config = await resp.json()
  return _config!
}

export function getConfig(): AppConfig {
  if (!_config) throw new Error('Config not loaded — call loadConfig() first')
  return _config
}
