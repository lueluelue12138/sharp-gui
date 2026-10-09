import {
  BadgeInfo,
  Bot,
  BookOpen,
  Camera,
  CircleHelp,
  Clock3,
  Cpu,
  ExternalLink,
  HardDrive,
  Layers3,
  Route,
  Settings2,
  Sparkles,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';

import { Modal } from '@/components/common/Modal';
import { useAppStore } from '@/store';

import styles from './VideoReconstructionGuide.module.css';

const README_ZH_URL = 'https://github.com/lueluelue12138/sharp-gui#视频重建环境手动搭建指南';
const README_EN_URL = 'https://github.com/lueluelue12138/sharp-gui/blob/main/README.en.md#video-reconstruction-manual-environment-setup';

const OVERVIEW_ITEMS = [
  { key: 'route', Icon: Route },
  { key: 'sampling', Icon: Clock3 },
  { key: 'scene', Icon: Layers3 },
  { key: 'result', Icon: Sparkles },
] as const;

const SHOOTING_TIPS = ['path', 'overlap', 'light', 'blur', 'long'] as const;
const PARAMETER_ITEMS = ['frames', 'iterations', 'resolution', 'matching', 'cache'] as const;

const DEPENDENCY_ITEMS = [
  { key: 'ffmpeg', Icon: Camera },
  { key: 'colmap', Icon: Route },
  { key: 'brush', Icon: Layers3 },
  { key: 'nerfstudio', Icon: Layers3 },
  { key: 'gpu', Icon: Cpu },
  { key: 'storage', Icon: HardDrive },
] as const;

export function VideoReconstructionGuide() {
  const { t } = useTranslation();
  const { isOpen, closeGuide } = useAppStore(
    useShallow((state) => ({
      isOpen: state.videoReconstructionGuideOpen,
      closeGuide: state.closeVideoReconstructionGuide,
    })),
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={closeGuide}
      title={t('videoReconGuideTitle')}
      size="lg"
    >
      <div className={styles.root}>
        <section className={styles.hero}>
          <span className={styles.eyebrow}>
            <BookOpen size={15} strokeWidth={1.8} />
            {t('videoReconGuideBadge')}
          </span>
          <h2>{t('videoReconGuideHeroTitle')}</h2>
          <p>{t('videoReconGuideHeroText')}</p>

          <div className={styles.factGrid}>
            <div>
              <span>{t('videoReconGuideFact.preview')}</span>
              <strong>{t('videoReconQualityMetaByEngine.brush.preview')}</strong>
            </div>
            <div>
              <span>{t('videoReconGuideFact.high')}</span>
              <strong>{t('videoReconQualityMetaByEngine.brush.high')}</strong>
            </div>
            <div>
              <span>{t('videoReconGuideFact.extreme')}</span>
              <strong>{t('videoReconQualityMetaByEngine.brush.extreme')}</strong>
            </div>
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionIcon}>
              <BadgeInfo size={17} strokeWidth={1.8} />
            </span>
            <div>
              <h3>{t('videoReconGuideBasicsTitle')}</h3>
              <p>{t('videoReconGuideBasicsText')}</p>
            </div>
          </div>

          <div className={styles.cardGrid}>
            {OVERVIEW_ITEMS.map(({ key, Icon }) => (
              <article className={styles.infoCard} key={key}>
                <span className={styles.cardIcon}>
                  <Icon size={18} strokeWidth={1.8} />
                </span>
                <h4>{t(`videoReconGuideOverview.${key}.title`)}</h4>
                <p>{t(`videoReconGuideOverview.${key}.text`)}</p>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionIcon}>
              <Camera size={17} strokeWidth={1.8} />
            </span>
            <div>
              <h3>{t('videoReconGuideShootTitle')}</h3>
              <p>{t('videoReconGuideShootText')}</p>
            </div>
          </div>

          <ul className={styles.tipList}>
            {SHOOTING_TIPS.map((tip) => (
              <li className={styles.tipItem} key={tip}>
                <span className={styles.tipMarker} />
                <div>
                  <strong>{t(`videoReconGuideTips.${tip}.title`)}</strong>
                  <p>{t(`videoReconGuideTips.${tip}.text`)}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionIcon}>
              <Settings2 size={17} strokeWidth={1.8} />
            </span>
            <div>
              <h3>{t('videoReconGuideParametersTitle')}</h3>
              <p>{t('videoReconGuideParametersText')}</p>
            </div>
          </div>

          <div className={styles.parameterGrid}>
            {PARAMETER_ITEMS.map((item) => (
              <article className={styles.parameterItem} key={item}>
                <strong>{t(`videoReconGuideParameters.${item}.title`)}</strong>
                <p>{t(`videoReconGuideParameters.${item}.text`)}</p>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionIcon}>
              <Cpu size={17} strokeWidth={1.8} />
            </span>
            <div>
              <h3>{t('videoReconGuideDependencyTitle')}</h3>
              <p>{t('videoReconGuideDependencyText')}</p>
            </div>
          </div>

          <div className={styles.dependencyGrid}>
            {DEPENDENCY_ITEMS.map(({ key, Icon }) => (
              <article className={styles.dependencyItem} key={key}>
                <Icon size={17} strokeWidth={1.8} />
                <div>
                  <strong>{t(`videoReconGuideDependencies.${key}.title`)}</strong>
                  <p>{t(`videoReconGuideDependencies.${key}.text`)}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionIcon}>
              <CircleHelp size={17} strokeWidth={1.8} />
            </span>
            <div>
              <h3>{t('videoReconGuideSetupTitle')}</h3>
              <p>{t('videoReconGuideSetupText')}</p>
            </div>
          </div>

          <div className={styles.setupPanel}>
            <article className={styles.setupItem}>
              <BookOpen size={17} strokeWidth={1.8} />
              <div>
                <strong>{t('videoReconGuideInstallTitle')}</strong>
                <p>{t('videoReconGuideInstallText')}</p>
                <div className={styles.linkRow}>
                  <a href={README_ZH_URL} target="_blank" rel="noreferrer">
                    {t('videoReconGuideReadReadme')}
                    <ExternalLink size={13} strokeWidth={1.8} />
                  </a>
                  <a href={README_EN_URL} target="_blank" rel="noreferrer">
                    {t('videoReconGuideReadReadmeEn')}
                    <ExternalLink size={13} strokeWidth={1.8} />
                  </a>
                </div>
              </div>
            </article>

            <article className={styles.setupItem}>
              <Bot size={17} strokeWidth={1.8} />
              <div>
                <strong>{t('videoReconGuideAgentTitle')}</strong>
                <p>{t('videoReconGuideAgentText')}</p>
                <pre className={styles.promptBlock}>
                  <code>{t('videoReconGuideAgentPrompt')}</code>
                </pre>
              </div>
            </article>
          </div>
        </section>
      </div>
    </Modal>
  );
}
