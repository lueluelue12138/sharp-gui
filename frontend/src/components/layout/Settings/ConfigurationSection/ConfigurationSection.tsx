import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FolderInput } from 'lucide-react';

import { ApiError, browseFolder, previewConfiguration, restoreConfiguration, waitForConfigurationRestart } from '@/api';
import { Button } from '@/components/common/Button';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { TextInputDialog } from '@/components/common/TextInputDialog';
import type { ConfigurationPreview } from '@/types/configuration';

import styles from './ConfigurationSection.module.css';

interface ConfigurationSectionProps {
  configFile: string;
  scope: 'global' | 'explicit';
}

export function ConfigurationSection({ configFile, scope }: ConfigurationSectionProps) {
  const { t } = useTranslation();
  const [preview, setPreview] = useState<ConfigurationPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [message, setMessage] = useState('');
  const showError = (error: unknown) => {
    const key = error instanceof ApiError && error.data?.code
      ? `configurationErrors.${error.data.code}` : 'configurationRestoreFailed';
    setMessage(t(key, { defaultValue: t('configurationRestoreFailed') }));
  };
  const chooseFolder = async () => {
    setBusy(true);
    setMessage('');
    try {
      let selected;
      try {
        selected = await browseFolder(t('configurationChooseOldFolder'));
      } catch (error) {
        // A headless host or an unavailable native picker still allows manual entry.
        if (error instanceof ApiError && error.status >= 500) {
          setManualOpen(true);
          return;
        }
        throw error;
      }
      if (selected.success && selected.path) setPreview(await previewConfiguration(selected.path));
      else if (selected.error) setManualOpen(true);
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
    }
  };
  const restore = async () => {
    if (!preview) return;
    setBusy(true);
    setMessage('');
    let saved = false;
    try {
      const result = await restoreConfiguration(preview);
      saved = true;
      setPreview(null);
      setMessage(t('configurationRestarting'));
      await waitForConfigurationRestart(result.server_instance_id);
      window.location.reload();
    } catch (error) {
      setPreview(null);
      if (saved) setMessage(t('configurationRestartFailed'));
      else showError(error);
      setBusy(false);
    }
  };
  const previewManual = async (folder: string) => {
    setBusy(true);
    try {
      setPreview(await previewConfiguration(folder));
      setManualOpen(false);
    } catch (error) {
      setManualOpen(false);
      showError(error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className={styles.section} aria-label={t('configurationTitle')}>
      <h3>{t('configurationTitle')}</h3>
      <p className={styles.path} data-tooltip={configFile}>{configFile}</p>
      <p>{t(scope === 'global' ? 'configurationGlobalHint' : 'configurationExplicitHint')}</p>
      <Button variant="secondary" size="sm" icon={<FolderInput size={15} />} disabled={busy} onClick={chooseFolder}>
        {t('configurationRestore')}
      </Button>
      {message && <p role="status" aria-live="polite">{message}</p>}
      <TextInputDialog
        isOpen={manualOpen}
        title={t('configurationChooseOldFolder')}
        label={t('configurationFolderPath')}
        placeholder={t('configurationFolderHint')}
        isBusy={busy}
        onClose={() => setManualOpen(false)}
        onSubmit={previewManual}
      />
      <ConfirmDialog
        isOpen={preview !== null}
        title={t('configurationRestore')}
        message={t('configurationRestoreConfirm', { workspace: preview?.workspace_folder, count: preview?.album_count })}
        confirmLabel={t('configurationRestoreAndRestart')}
        isBusy={busy}
        onClose={() => setPreview(null)}
        onConfirm={restore}
      />
    </section>
  );
}
