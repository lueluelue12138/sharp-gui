import { useState } from 'react';
import type { FormEvent } from 'react';

import { KeyRound, LockKeyhole, ShieldCheck, Unlock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';

import { ApiError, loginWithAccessCode, loginWithOwnerToken } from '@/api';
import { useAppStore } from '@/store';

import styles from './AccessGate.module.css';

interface AccessGateProps {
  onUnlocked: () => Promise<void> | void;
}

export function AccessGate({ onUnlocked }: AccessGateProps) {
  const { t } = useTranslation();
  const [password, setPassword] = useState('');
  const [ownerToken, setOwnerToken] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isOwnerSubmitting, setIsOwnerSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ownerError, setOwnerError] = useState<string | null>(null);

  const { authStatus, setAuthStatus } = useAppStore(
    useShallow((state) => ({
      authStatus: state.authStatus,
      setAuthStatus: state.setAuthStatus,
    })),
  );

  const setupRequired = authStatus?.setup_required ?? false;
  const canUseOwnerBootstrap = setupRequired && Boolean(authStatus?.owner_bootstrap_available);

  // HTTP（非加密）模式下访问码与会话明文传输，对局域网/远程访问者给出安全提示。
  // 本机 loopback 访问无明文嗅探风险，不打扰。
  const isInsecureConnection =
    typeof window !== 'undefined' &&
    window.location.protocol !== 'https:' &&
    !['localhost', '127.0.0.1', '::1'].includes(window.location.hostname);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (setupRequired || isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const nextStatus = await loginWithAccessCode({ password });
      setAuthStatus(nextStatus);
      setPassword('');
      await onUnlocked();
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.data?.code === 'ACCESS_SETUP_REQUIRED'
          ? t('accessGateSetupRequired')
          : t('accessGateInvalidCode'));
      } else {
        setError(t('accessGateLoginFailed'));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleOwnerSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canUseOwnerBootstrap || isOwnerSubmitting) {
      return;
    }

    setIsOwnerSubmitting(true);
    setOwnerError(null);
    try {
      const nextStatus = await loginWithOwnerToken({ token: ownerToken });
      setAuthStatus(nextStatus);
      setOwnerToken('');
      await onUnlocked();
    } catch (caught) {
      if (caught instanceof ApiError && caught.data?.code === 'INVALID_OWNER_TOKEN') {
        setOwnerError(t('dockerOwnerTokenInvalid'));
      } else {
        setOwnerError(t('dockerOwnerTokenFailed'));
      }
    } finally {
      setIsOwnerSubmitting(false);
    }
  };

  return (
    <main className={styles.shell}>
      <section className={styles.panel}>
        <div className={styles.iconWrap}>
          {setupRequired ? <ShieldCheck size={28} /> : <LockKeyhole size={28} />}
        </div>
        <h1 className={styles.title}>{t('accessGateTitle')}</h1>
        <p className={styles.subtitle}>
          {setupRequired ? t('accessGateSetupRequired') : t('accessGateSubtitle')}
        </p>

        {!setupRequired && isInsecureConnection ? (
          <p className={styles.insecureNotice}>{t('accessGateHttpWarning')}</p>
        ) : null}

        {canUseOwnerBootstrap ? (
          <form className={styles.form} onSubmit={handleOwnerSubmit}>
            <div className={styles.ownerCard}>
              <div className={styles.ownerCardHeader}>
                <KeyRound size={18} />
                <span>{t('dockerOwnerTitle')}</span>
              </div>
              <p>{t('dockerOwnerDescription')}</p>
              <p className={styles.ownerHint}>{t('dockerOwnerTokenHint')}</p>
            </div>
            <label className={styles.label} htmlFor="docker-owner-token">
              {t('dockerOwnerTokenLabel')}
            </label>
            <input
              id="docker-owner-token"
              className={styles.input}
              type="password"
              autoComplete="one-time-code"
              value={ownerToken}
              onChange={(event) => setOwnerToken(event.target.value)}
              placeholder={t('dockerOwnerTokenPlaceholder')}
              disabled={isOwnerSubmitting}
              autoFocus
            />
            {ownerError ? <p className={styles.error}>{ownerError}</p> : null}
            <button className={styles.submit} type="submit" disabled={!ownerToken || isOwnerSubmitting}>
              <Unlock size={18} />
              <span>{isOwnerSubmitting ? t('dockerOwnerUnlocking') : t('dockerOwnerUnlock')}</span>
            </button>
          </form>
        ) : null}

        {!setupRequired && (
          <form className={styles.form} onSubmit={handleSubmit}>
            <label className={styles.label} htmlFor="access-code">
              {t('accessGateCodeLabel')}
            </label>
            <input
              id="access-code"
              className={styles.input}
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={t('accessGateCodePlaceholder')}
              disabled={isSubmitting}
              autoFocus
            />
            {error ? <p className={styles.error}>{error}</p> : null}
            <button className={styles.submit} type="submit" disabled={!password || isSubmitting}>
              <Unlock size={18} />
              <span>{isSubmitting ? t('accessGateUnlocking') : t('accessGateUnlock')}</span>
            </button>
          </form>
        )}
      </section>
    </main>
  );
}
