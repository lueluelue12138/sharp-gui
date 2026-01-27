import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './en.json';
import zh from './zh.json';

// 检测浏览器语言
function detectLanguage(): string {
  const savedLang = localStorage.getItem('sharp-gui-lang');
  if (savedLang && ['en', 'zh'].includes(savedLang)) {
    return savedLang;
  }
  
  const browserLang = navigator.language.toLowerCase();
  if (browserLang.startsWith('zh')) {
    return 'zh';
  }
  return 'en';
}

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      zh: { translation: zh },
    },
    lng: detectLanguage(),
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false, // React 已经处理 XSS
    },
  });

// 语言切换函数
export function toggleLanguage() {
  const newLang = i18n.language === 'en' ? 'zh' : 'en';
  i18n.changeLanguage(newLang);
  localStorage.setItem('sharp-gui-lang', newLang);
}

export default i18n;
