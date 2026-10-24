import en from '../../../packages/i18n/en.json';
import ht from '../../../packages/i18n/ht.json';
import fr from '../../../packages/i18n/fr.json';
import pt from '../../../packages/i18n/pt-BR.json';
import es from '../../../packages/i18n/es.json';
import ar from '../../../packages/i18n/ar.json';
import zh from '../../../packages/i18n/zh-Hans.json';
import id from '../../../packages/i18n/id.json';
import sw from '../../../packages/i18n/sw.json';
export const languages: Record<string, string> = {
  ht: 'Kreyòl ayisyen',
  en: 'English',
  fr: 'Français',
  'pt-BR': 'Português (Brasil)',
  es: 'Español',
  ar: 'العربية',
  'zh-Hans': '简体中文',
  id: 'Bahasa Indonesia',
  sw: 'Kiswahili',
};
export const dictionaries: Record<string, Record<string, string>> = {
  en,
  ht,
  fr,
  'pt-BR': pt,
  es,
  ar,
  'zh-Hans': zh,
  id,
  sw,
};
