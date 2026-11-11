/** Offline suggestions shared by web/mobile. The editable prompt is the only state. */
export const MUSIC_STYLE_MAX_LENGTH = 1000;
export const musicStyleSuggestions = [
  { text: 'Konpa' }, { text: 'Afrobeats' }, { text: 'Gospel' },
  { text: 'Rap' }, { text: 'R&B' }, { text: 'Zouk' },
  { text: 'Amapiano' }, { text: 'Pop' },
  { key: 'musicSuggestPiano' }, { key: 'musicSuggestGuitar' },
  { key: 'musicSuggestBass' }, { key: 'musicSuggestPercussion' },
  { key: 'musicSuggestHopeful' }, { key: 'musicSuggestRomantic' },
  { key: 'musicSuggestEnergetic' }, { text: '90 BPM' }, { text: '110 BPM' },
  { key: 'maleVocal' }, { key: 'femaleVocal' },
  { key: 'duetVocal' }, { key: 'instrumentalVocal' },
];

export function hasStyleSuggestion(prompt: string, suggestion: string) {
  return prompt.split(/[,;\n]+/).some(part => part.trim().toLowerCase() === suggestion.toLowerCase());
}

export function toggleStyleSuggestion(prompt: string, suggestion: string) {
  if (hasStyleSuggestion(prompt, suggestion)) {
    const remaining = prompt.split(/[,;\n]+/).map(part => part.trim()).filter(part => part && part.toLowerCase() !== suggestion.toLowerCase());
    const next = remaining.join(', ');
    return next.length <= MUSIC_STYLE_MAX_LENGTH ? next : remaining.join(',');
  }
  const next = prompt.trimEnd() + (prompt.trim() ? ', ' : '') + suggestion;
  return next.length <= MUSIC_STYLE_MAX_LENGTH ? next : prompt;
}
