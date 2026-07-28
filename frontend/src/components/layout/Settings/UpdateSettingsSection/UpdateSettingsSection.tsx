import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  ApiError,
  applyUpdate,
  checkForUpdates,
  fetchUpdateStatus,
  isActiveUpdateOperation,
  pollUpdateStatus,
} from '@/api';
import { Button } from '@/components/common/Button';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import {
  ClockIcon,
  DownloadIcon,
  InfoIcon,
  ResetIcon,
} from '@/components/common/Icons';
import type {
  UpdateCandidate,
  UpdateChannel,
  UpdateStatusResponse,
  UpdateTimestamp,
} from '@/types';

import styles from './UpdateSettingsSection.module.css';

interface UpdateSettingsSectionProps {
  active: boolean;
  isOwner: boolean;
}

interface OperationTracker {
  token: number;
  startedInstanceId: string;
  expectedCommit: string;
}

type BusyAction = 'check' | 'apply' | null;

const DEFAULT_UPDATE_BRANCH = 'main';
const UPDATE_MANIFEST_PATH = 'update-manifest.json';
const FAILURE_PHASES = new Set(['cancelled', 'failed']);

// Mirrors the phases produced by backend/services/self_update.py.
const PHASE_KEYS: Record<string, string> = {
  queued: 'updatePhaseQueued',
  waiting_for_server: 'updatePhaseWaitingForServer',
  fetching: 'updatePhaseFetching',
  applying: 'updatePhaseApplying',
  verifying: 'updatePhaseVerifying',
  rolling_back: 'updatePhaseRollingBack',
  restarting: 'updatePhaseRestarting',
  completed: 'updatePhaseCompleted',
  failed: 'updatePhaseFailed',
};

const RELATION_KEYS: Record<string, string> = {
  same: 'updateRelationSame',
  current: 'updateRelationSame',
  ahead: 'updateRelationAhead',
  upgrade: 'updateRelationAhead',
  behind: 'updateRelationBehind',
  downgrade: 'updateRelationBehind',
  diverged: 'updateRelationDiverged',
  unknown: 'updateRelationUnknown',
};

const INSTALLATION_KEYS: Record<string, string> = {
  source: 'updateInstallationSource',
  release: 'updateInstallationRelease',
  portable: 'updateInstallationPortable',
  unknown: 'updateInstallationUnknown',
};

// Every stable code the backend can return through /api/updates/*. Keep this in
// sync with the UpdateError codes in backend/services/self_update.py.
const CODE_KEYS: Record<string, string> = {
  update_already_current: 'updateErrorAlreadyCurrent',
  update_apply_failed: 'updateErrorApplyFailed',
  update_bootstrap_required: 'updateErrorInstallationUnsupported',
  update_channel_invalid: 'updateErrorRequestInvalid',
  update_check_failed: 'updateErrorCheckFailed',
  update_developer_branch: 'updateReasonNonDefaultBranch',
  update_frontend_missing: 'updateCompatibilityFrontendMissing',
  update_full_package_required: 'updateCompatibilityFullPackageRequired',
  update_git_failed: 'updateErrorGitFailed',
  update_git_too_old: 'updateCompatibilityGitTooOld',
  update_git_unavailable: 'updateReasonGitUnavailable',
  update_helper_missing: 'updateErrorHelperMissing',
  update_helper_start_failed: 'updateErrorHelperFailed',
  update_in_progress: 'updateReasonOperationInProgress',
  update_incompatible: 'updateCompatibilityFullPackageRequired',
  update_installation_unsupported: 'updateErrorInstallationUnsupported',
  update_installed_revision_changed: 'updateErrorRevisionChanged',
  update_interrupted_rolled_back: 'updateErrorRolledBack',
  update_manifest_invalid: 'updateCompatibilityManifestInvalid',
  update_manifest_missing: 'updateCompatibilityManifestMissing',
  update_not_supported: 'updateErrorInstallationUnsupported',
  update_operation_invalid: 'updateErrorOperationInvalid',
  update_owner_required: 'updateReasonOwnerRequired',
  update_protocol_incompatible: 'updateCompatibilityProtocolMismatch',
  update_recovery_required: 'updateErrorRecoveryRequired',
  update_release_invalid: 'updateErrorTargetInvalid',
  update_request_invalid: 'updateErrorRequestInvalid',
  update_restart_failed: 'updateErrorRestartFailed',
  update_rollback_failed: 'updateErrorRollbackFailed',
  update_server_stop_timeout: 'updateErrorServerStopTimeout',
  update_target_changed: 'updateErrorTargetChanged',
  update_target_expired: 'updateErrorTargetExpired',
  update_target_invalid: 'updateErrorTargetInvalid',
  update_target_tracks_runtime: 'updateErrorTargetTracksRuntime',
  update_target_unsupported: 'updateCompatibilityPackageTarget',
  update_target_untrusted: 'updateCompatibilityTargetUntrusted',
  update_tasks_active: 'updateReasonActiveTasks',
  update_verification_failed: 'updateErrorVerificationFailed',
  update_worktree_dirty: 'updateReasonDirtyWorktree',
};

const ADVISORY_KEYS: Record<string, string> = {
  update_runtime_revision_changed: 'updateAdvisoryRuntimeChanged',
};

type BlockerScope = 'current' | 'target' | 'operation';

interface UpdateBlocker {
  scope: BlockerScope;
  code: string | null;
  messageKey: string;
}

function normalizeCode(value?: string | null): string {
  return value?.trim().toLowerCase() ?? '';
}

function codeKey(value?: string | null): string {
  return CODE_KEYS[normalizeCode(value)] ?? 'updateUnknownError';
}

function apiErrorKey(error: ApiError, fallbackKey: string): string {
  return error.data?.code ? codeKey(error.data.code) : fallbackKey;
}

function formatTimestamp(value: UpdateTimestamp, locale: string): string | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

function commitsMatch(left?: string | null, right?: string | null): boolean {
  if (!left || !right) {
    return false;
  }
  const a = left.toLowerCase();
  const b = right.toLowerCase();
  return a === b || a.startsWith(b) || b.startsWith(a);
}

function isDowngrade(candidate?: UpdateCandidate | null): boolean {
  return candidate?.relation === 'behind' || candidate?.relation === 'downgrade';
}

export function UpdateSettingsSection({ active, isOwner }: UpdateSettingsSectionProps) {
  const { t, i18n } = useTranslation();
  const [status, setStatus] = useState<UpdateStatusResponse | null>(null);
  const [selectedChannel, setSelectedChannel] = useState<UpdateChannel>('stable');
  const [isLoading, setIsLoading] = useState(false);
  const [busyAction, setBusyAction] = useState<BusyAction>(null);
  const [confirmation, setConfirmation] = useState<UpdateCandidate | null>(null);
  const [viewErrorKey, setViewErrorKey] = useState<string | null>(null);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [tracker, setTracker] = useState<OperationTracker | null>(null);
  const reloadStartedRef = useRef(false);

  const candidate = status?.channels[selectedChannel] ?? null;
  const operation = status?.operation ?? null;
  const operationActive = isActiveUpdateOperation(operation);
  const effectiveOwner = isOwner && (status?.is_owner ?? true);
  const actionsLocked = Boolean(busyAction || operationActive || tracker);
  const checkedAt = formatTimestamp(
    candidate?.checked_at ?? status?.checked_at ?? null,
    i18n.resolvedLanguage ?? i18n.language,
  );
  const capabilities = status?.capabilities;
  // Blockers of the current installation. An active operation already explains
  // itself through the progress panel, so its reasons are not repeated here.
  const currentCodes = !effectiveOwner
    ? ['update_owner_required']
    : operationActive
      ? []
      : capabilities?.reason_codes
        ?? (capabilities?.reason_code ? [capabilities.reason_code] : []);
  const targetCode = candidate && !candidate.compatible
    ? candidate.compatibility_code
    : !candidate && currentCodes.length === 0
      ? status?.last_check_error_code ?? null
      : null;
  const advisoryKey = candidate?.compatible && candidate.advisory_code
    ? ADVISORY_KEYS[normalizeCode(candidate.advisory_code)] ?? null
    : null;

  const blockers: UpdateBlocker[] = [];
  const seenMessageKeys = new Set<string>();
  const addBlocker = (scope: BlockerScope, code: string | null, messageKey: string) => {
    if (!messageKey || seenMessageKeys.has(messageKey)) {
      return;
    }
    seenMessageKeys.add(messageKey);
    blockers.push({ scope, code: code ? normalizeCode(code) : null, messageKey });
  };
  currentCodes.forEach((code) => addBlocker('current', code, codeKey(code)));
  if (targetCode) {
    addBlocker('target', targetCode, codeKey(targetCode));
  }
  if (operation?.error_code) {
    addBlocker('operation', operation.error_code, codeKey(operation.error_code));
  }
  if (viewErrorKey) {
    // viewErrorKey is already a translation key, not a backend code.
    addBlocker('operation', null, viewErrorKey);
  }

  const phaseKey = PHASE_KEYS[normalizeCode(operation?.phase)] ?? 'updatePhaseWorking';
  const relationKey = RELATION_KEYS[normalizeCode(candidate?.relation)] ?? 'updateRelationUnknown';
  const installationKey = INSTALLATION_KEYS[normalizeCode(status?.current.installation_kind)]
    ?? 'updateInstallationUnknown';
  const canCheck = effectiveOwner
    && Boolean(status?.capabilities.can_check)
    && !actionsLocked;
  const canApply = effectiveOwner
    && Boolean(status?.capabilities.can_apply)
    && Boolean(candidate?.update_available)
    && Boolean(candidate?.compatible)
    && !actionsLocked;

  useEffect(() => {
    if (!active) {
      setConfirmation(null);
      return undefined;
    }

    const controller = new AbortController();
    setIsLoading(true);
    setViewErrorKey(null);
    fetchUpdateStatus({ signal: controller.signal })
      .then((nextStatus) => {
        setStatus(nextStatus);
        if (nextStatus.current.channel === 'stable' || nextStatus.current.channel === 'latest') {
          setSelectedChannel(nextStatus.current.channel);
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setViewErrorKey(
            error instanceof ApiError
              ? apiErrorKey(error, 'updateErrorStatusFailed')
              : 'updateErrorStatusFailed',
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      });

    return () => controller.abort();
  }, [active]);

  const activeOperationId = operationActive ? operation?.id ?? null : null;

  useEffect(() => {
    if (!active || !status || (!activeOperationId && !tracker)) {
      return undefined;
    }

    const controller = new AbortController();
    const initialStatus = status;
    const startedInstanceId = tracker?.startedInstanceId ?? initialStatus.server_instance_id;
    let expectedCommit = tracker?.expectedCommit ?? initialStatus.operation?.target_sha ?? '';
    let operationSeen = isActiveUpdateOperation(initialStatus.operation);

    setIsReconnecting(false);
    pollUpdateStatus({
      initialStatus,
      signal: controller.signal,
      onStatus: (nextStatus) => {
        setStatus(nextStatus);
        setIsReconnecting(false);
        expectedCommit ||= nextStatus.operation?.target_sha ?? '';
        operationSeen ||= Boolean(nextStatus.operation?.id);
      },
      onTransientError: () => setIsReconnecting(true),
      shouldStop: (nextStatus) => {
        const instanceChanged = nextStatus.server_instance_id !== startedInstanceId;
        const targetReached = commitsMatch(nextStatus.current.commit, expectedCommit);
        if (instanceChanged && targetReached && !reloadStartedRef.current) {
          reloadStartedRef.current = true;
          window.location.reload();
          return true;
        }
        if (isActiveUpdateOperation(nextStatus.operation) || !operationSeen) {
          return false;
        }
        return true;
      },
    })
      .then((finalStatus) => {
        setStatus(finalStatus);
        setTracker(null);
        setIsReconnecting(false);
        if (finalStatus.operation?.error_code) {
          setViewErrorKey(codeKey(finalStatus.operation.error_code));
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setTracker(null);
          setIsReconnecting(false);
          setViewErrorKey(
            error instanceof ApiError
              ? apiErrorKey(error, 'updateReconnectTimeout')
              : 'updateReconnectTimeout',
          );
        }
      });

    return () => controller.abort();
    // Poll callbacks consume phase/progress changes; restart only for a new operation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, activeOperationId, tracker?.token]);

  const handleRetryStatus = async () => {
    setIsLoading(true);
    setViewErrorKey(null);
    try {
      setStatus(await fetchUpdateStatus());
    } catch (error) {
      setViewErrorKey(
        error instanceof ApiError
          ? apiErrorKey(error, 'updateErrorStatusFailed')
          : 'updateErrorStatusFailed',
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleCheck = async () => {
    if (!canCheck) {
      return;
    }
    setBusyAction('check');
    setViewErrorKey(null);
    try {
      setStatus(await checkForUpdates(selectedChannel));
    } catch (error) {
      setViewErrorKey(
        error instanceof ApiError
          ? apiErrorKey(error, 'updateErrorCheckFailed')
          : 'updateErrorCheckFailed',
      );
    } finally {
      setBusyAction(null);
    }
  };

  const handleApply = async (target: UpdateCandidate) => {
    if (!status || !canApply) {
      return;
    }

    const startedInstanceId = status.server_instance_id;
    setBusyAction('apply');
    setViewErrorKey(null);
    try {
      const nextStatus = await applyUpdate({ channel: target.channel });
      setStatus(nextStatus);
      if (!FAILURE_PHASES.has(normalizeCode(nextStatus.operation?.phase))
          && !nextStatus.operation?.error_code) {
        setTracker({
          token: Date.now(),
          startedInstanceId,
          expectedCommit: target.target_sha,
        });
      }
      setConfirmation(null);
    } catch (error) {
      if (!(error instanceof ApiError)) {
        setTracker({
          token: Date.now(),
          startedInstanceId,
          expectedCommit: target.target_sha,
        });
        setIsReconnecting(true);
        setConfirmation(null);
      } else {
        setViewErrorKey(apiErrorKey(error, 'updateErrorApplyFailed'));
      }
    } finally {
      setBusyAction(null);
    }
  };

  const confirmationMessage = confirmation?.channel === 'latest'
    ? t('updateConfirmLatest', { version: confirmation.display_version })
    : isDowngrade(confirmation)
      ? t('updateConfirmDowngrade', { version: confirmation?.display_version ?? '' })
      : t('updateConfirmStable', { version: confirmation?.display_version ?? '' });

  return (
    <section className={styles.section} aria-labelledby="update-settings-title">
      <span className={styles.sectionLabel}>{t('updateCenterSectionLabel')}</span>
      <div className={styles.card}>
        <header className={styles.header}>
          <div className={styles.headerIcon} aria-hidden="true">
            <ResetIcon />
          </div>
          <div className={styles.headerCopy}>
            <h4 id="update-settings-title">{t('updateCenterTitle')}</h4>
            <p>{t('updateCenterDescription')}</p>
          </div>
          {status && (
            <span className={`${styles.stateBadge} ${
              operationActive
                ? styles.stateBusy
                : blockers.length > 0
                  ? styles.stateWarning
                  : styles.stateReady
            }`}>
              {operationActive
                ? t(phaseKey)
                : blockers.length > 0
                  ? t('updateNeedsAttention')
                  : t('updateReady')}
            </span>
          )}
        </header>

        {isLoading && !status ? (
          <div className={styles.loadingState} role="status">
            <ClockIcon aria-hidden="true" />
            <span>{t('updateLoadingStatus')}</span>
          </div>
        ) : status ? (
          <>
            <dl className={styles.versionGrid}>
              <div>
                <dt>{t('updateInstalledVersion')}</dt>
                <dd>{status.current.display_version || t('updateUnknown')}</dd>
              </div>
              <div>
                <dt>{t('updateCurrentCommit')}</dt>
                <dd className={styles.mono}>
                  {status.current.short_commit || status.current.commit || t('updateUnknown')}
                </dd>
              </div>
              <div>
                <dt>{t('updateInstallation')}</dt>
                <dd>{t(installationKey)}</dd>
              </div>
              <div>
                <dt>{t('updateBranch')}</dt>
                <dd className={styles.mono}>{status.current.branch || t('updateUnknown')}</dd>
              </div>
            </dl>

            <div className={styles.channelBlock}>
              <div className={styles.blockHeading}>
                <span>{t('updateChannel')}</span>
                <span>
                  {checkedAt
                    ? t('updateLastChecked', { time: checkedAt })
                    : t('updateNeverChecked')}
                </span>
              </div>
              <div className={styles.channelSelector}>
                {(['stable', 'latest'] as UpdateChannel[]).map((channel) => (
                  <button
                    className={`${styles.channelButton} ${
                      channel === selectedChannel ? styles.channelButtonSelected : ''
                    }`}
                    disabled={actionsLocked}
                    key={channel}
                    onClick={() => {
                      setSelectedChannel(channel);
                      setViewErrorKey(null);
                    }}
                    type="button"
                  >
                    <span>
                      {channel === 'stable'
                        ? t('updateChannelStable')
                        : t('updateChannelLatest')}
                    </span>
                    <small>
                      {channel === 'stable'
                        ? t('updateStableDescription')
                        : t('updateLatestDescription')}
                    </small>
                  </button>
                ))}
              </div>
            </div>

            {candidate ? (
              <div className={styles.candidateCard}>
                <div className={styles.candidateHeader}>
                  <div>
                    <span>{t('updateTargetVersion')}</span>
                    <strong>{candidate.display_version}</strong>
                  </div>
                  <span className={candidate.compatible ? styles.compatible : styles.incompatible}>
                    {candidate.compatible ? t('updateCompatible') : t('updateIncompatible')}
                  </span>
                </div>
                <dl className={styles.candidateDetails}>
                  <div>
                    <dt>{t('updateTargetCommit')}</dt>
                    <dd className={styles.mono}>{candidate.short_sha}</dd>
                  </div>
                  <div>
                    <dt>{t('updateRelation')}</dt>
                    <dd>{t(relationKey)}</dd>
                  </div>
                </dl>
                {!candidate.update_available && candidate.compatible && (
                  <p className={styles.upToDate}>{t('updateUpToDate')}</p>
                )}
              </div>
            ) : (
              <p className={styles.emptyHint}>{t('updateNotChecked')}</p>
            )}

            {selectedChannel === 'latest' && (
              <div className={`${styles.notice} ${styles.warningNotice}`} role="note">
                <InfoIcon aria-hidden="true" />
                <div>
                  <strong>{t('updateLatestRiskTitle')}</strong>
                  <p>{t('updateLatestRisk')}</p>
                </div>
              </div>
            )}

            {advisoryKey && (
              <div className={`${styles.notice} ${styles.warningNotice}`} role="note">
                <InfoIcon aria-hidden="true" />
                <div>
                  <strong>{t('updateAdvisoryTitle')}</strong>
                  <p>{t(advisoryKey)}</p>
                </div>
              </div>
            )}

            {blockers.length > 0 && (
              <div className={`${styles.notice} ${styles.errorNotice}`} role="alert">
                <InfoIcon aria-hidden="true" />
                <div className={styles.blockerContent}>
                  <strong>{t('updateErrorTitle')}</strong>
                  <ul className={styles.blockerList}>
                    {blockers.map((blocker) => (
                      <li className={styles.blockerItem} key={blocker.messageKey}>
                        <span>
                          {blocker.scope === 'current'
                            ? t('updateBlockerCurrentInstallation')
                            : blocker.scope === 'operation'
                              ? t('updateBlockerOperation')
                              : t('updateBlockerTarget', {
                                channel: selectedChannel === 'stable'
                                  ? t('updateChannelStable')
                                  : t('updateChannelLatest'),
                              })}
                        </span>
                        <small>{t(blocker.messageKey)}</small>
                        {blocker.code === 'update_developer_branch' && (
                          <small>
                            {t('updateBlockerBranchDetail', {
                              branch: status.current.branch || t('updateUnknown'),
                              defaultBranch: DEFAULT_UPDATE_BRANCH,
                            })}
                          </small>
                        )}
                        {blocker.code === 'update_manifest_missing' && (
                          <small>
                            {t('updateBlockerManifestDetail', { file: UPDATE_MANIFEST_PATH })}
                          </small>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {(operationActive || operation?.error_code) && (
              <div className={styles.operationPanel} role="status">
                <div className={styles.operationHeader}>
                  <strong>{t(phaseKey)}</strong>
                  <span>{Math.max(0, Math.min(100, operation?.progress ?? 0))}%</span>
                </div>
                <div
                  aria-label={t(phaseKey)}
                  aria-valuemax={100}
                  aria-valuemin={0}
                  aria-valuenow={typeof operation?.progress === 'number'
                    ? Math.max(0, Math.min(100, operation.progress))
                    : undefined}
                  className={styles.progressTrack}
                  role="progressbar"
                >
                  <span
                    className={`${styles.progressFill} ${
                      operation?.progress === null ? styles.progressIndeterminate : ''
                    }`}
                    style={{
                      width: operation?.progress === null
                        ? undefined
                        : `${Math.max(0, Math.min(100, operation?.progress ?? 0))}%`,
                    }}
                  />
                </div>
                {isReconnecting && <p>{t('updateConnectionInterruptedHint')}</p>}
              </div>
            )}

            {operation?.rolled_back && (
              <div className={`${styles.notice} ${styles.warningNotice}`} role="status">
                <InfoIcon aria-hidden="true" />
                <div>
                  <strong>{t('updateAutomaticRollbackTitle')}</strong>
                  <p>{t('updateAutomaticRollbackComplete')}</p>
                </div>
              </div>
            )}

            <div className={styles.actions}>
              <Button
                disabled={!canCheck}
                icon={<ResetIcon />}
                onClick={handleCheck}
                type="button"
                variant="secondary"
              >
                {busyAction === 'check'
                  ? t('updateChecking')
                  : candidate
                    ? t('updateRetry')
                    : t('updateCheck')}
              </Button>
              {candidate?.update_available && (
                <Button
                  disabled={!canApply}
                  icon={<DownloadIcon />}
                  onClick={() => setConfirmation(candidate)}
                  type="button"
                >
                  {isDowngrade(candidate)
                    ? t('updateSwitchStable')
                    : candidate.channel === 'latest'
                      ? t('updateApplyLatest')
                      : t('updateApply')}
                </Button>
              )}
            </div>
          </>
        ) : (
          <div className={styles.statusFailure}>
            <p>{t(viewErrorKey ?? 'updateErrorStatusFailed')}</p>
            <Button onClick={handleRetryStatus} type="button" variant="secondary">
              {t('updateRetry')}
            </Button>
          </div>
        )}
      </div>

      <ConfirmDialog
        confirmLabel={t('updateConfirmApply')}
        isBusy={busyAction === 'apply'}
        isOpen={Boolean(confirmation)}
        message={confirmationMessage}
        onClose={() => setConfirmation(null)}
        onConfirm={() => {
          if (confirmation) {
            void handleApply(confirmation);
          }
        }}
        title={t('updateConfirmTitle')}
      />
    </section>
  );
}
