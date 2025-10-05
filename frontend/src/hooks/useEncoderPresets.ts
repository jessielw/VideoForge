/**
 * Hook for managing encoder presets (save/load/delete)
 * Uses backend API for persistent storage across devices
 */

import { useState, useEffect } from 'react';
import { EncoderPreset } from '../types/encoder';

const API_BASE = 'http://localhost:8000';

export function useEncoderPresets() {
  const [allPresets, setAllPresets] = useState<EncoderPreset[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load all presets from backend API on mount
  useEffect(() => {
    loadPresets();
  }, []);

  const loadPresets = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/presets`);
      if (!response.ok) {
        throw new Error(`Failed to load presets: ${response.statusText}`);
      }
      const data = await response.json();

      // Transform backend response (snake_case) to frontend format (camelCase)
      const presets: EncoderPreset[] = data.map((p: any) => ({
        id: p.id,
        name: p.name,
        description: p.description,
        encoder: p.encoder,
        mode: p.rate_control_mode,
        crf: p.crf,
        bitrate: p.target_bitrate,
        preset: p.preset,
        tune: p.tune,
        customArgs: p.custom_args,
        isBuiltIn: p.is_builtin,
        createdAt: p.created_at,
        updatedAt: p.updated_at,
      }));

      setAllPresets(presets);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load presets';
      setError(errorMessage);
      console.error('Failed to load encoder presets:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // Save a new preset
  const savePreset = async (
    preset: Omit<EncoderPreset, 'id' | 'isBuiltIn' | 'createdAt' | 'updatedAt'>
  ): Promise<void> => {
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/presets`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: preset.name,
          description: preset.description,
          encoder: preset.encoder,
          rate_control_mode: preset.mode,
          crf: preset.crf,
          target_bitrate: preset.bitrate,
          preset: preset.preset,
          tune: preset.tune,
          custom_args: preset.customArgs,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to save preset: ${response.statusText}`);
      }

      // Reload presets from server
      await loadPresets();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to save preset';
      setError(errorMessage);
      console.error('Failed to save preset:', err);
      throw err;
    }
  };

  // Delete a custom preset
  const deletePreset = async (id: string): Promise<void> => {
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/presets/${id}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `Failed to delete preset: ${response.statusText}`);
      }

      // Reload presets from server
      await loadPresets();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to delete preset';
      setError(errorMessage);
      console.error('Failed to delete preset:', err);
      throw err;
    }
  };

  // Get preset by ID
  const getPreset = (id: string): EncoderPreset | undefined => {
    return allPresets.find(p => p.id === id);
  };

  const customPresets = allPresets.filter(p => !p.isBuiltIn);
  const builtInPresets = allPresets.filter(p => p.isBuiltIn);

  return {
    allPresets,
    customPresets,
    builtInPresets,
    savePreset,
    deletePreset,
    getPreset,
    isLoading,
    error,
    reload: loadPresets,
  };
}
