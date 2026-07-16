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

const PHASE_KEYS: Record<string, string> = {
  queued: 'updatePhaseQueued',
  fetching: 'updatePhaseFetching',
  validating: 'updatePhaseValidating',
  waiting_for_server: 'updatePhaseWaitingForServer',
  stopping: 'updatePhaseStopping',
  applying: 'updatePhaseApplying',
  checking_out: 'updatePhaseCheckingOut',
  verifying: 'updatePhaseVerifying',
  restarting: 'updatePhaseRestarting',
  completed: 'updatePhaseCompleted',
  failed: 'updatePhaseFailed',
  rolling_back: 'updatePhaseRollingBack',
  rollback_verifying: 'updatePhaseRollbackVerifying',
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

const CODE_KEYS: Record<string, string> = {
  update_owner_required: 'updateReasonOwnerRequired',
  update_git_unavailable: 'updateReasonGitUnavailable',
  update_git_too_old: 'updateCompatibilityGitTooOld',
  update_manifest_missing: 'updateCompatibilityManifestMissing',
  update_manifest_invalid: 'updateCompatibilityManifestInvalid',
  update_bootstrap_required: 'updateErrorInstallationUnsupported',
  update_installation_unsupported: 'updateErrorInstallationUnsupported',
  update_developer_branch: 'updateReasonNonDefaultBranch',
  update_worktree_dirty: 'updateReasonDirtyWorktree',
  update_tasks_active: 'updateReasonActiveTasks',
  update_in_progress: 'updateReasonOperationInProgress',
  update_runtime_incompatible: 'updateCompatibilityRuntimeMismatch',
  update_protocol_incompatible: 'updateCompatibilityProtocolMismatch',
  update_package_target_unsupported: 'updateCompatibilityPackageTarget',
  update_frontend_missing: 'updateCompatibilityFrontendMissing',
  update_target_untrusted: 'updateCompatibilityTargetUntrusted',
  update_target_expired: 'updateErrorTargetExpired',
  update_full_package_required: 'updateCompatibilityFullPackageRequired',
  update_incompatible: 'updateCompatibilityFullPackageRequired',
  update_channel_invalid: 'updateErrorRequestInvalid',
  update_already_current: 'updateErrorAlreadyCurrent',
  update_installed_revision_changed: 'updateErrorRevisionChanged',
  update_interrupted_rolled_back: 'updateErrorRolledBack',
  update_operation_invalid: 'updateErrorOperationInvalid',
  update_not_supported: 'updateErrorInstallationUnsupported',
  update_recovery_required: 'updateErrorRecoveryRequired',
  update_release_invalid: 'updateErrorTargetInvalid',
  update_rollback_failed: 'updateErrorRollbackFailed',
  update_server_stop_timeout: 'updateErrorServerStopTimeout',
  update_target_changed: 'updateErrorTargetChanged',
  update_target_tracks_runtime: 'updateErrorTargetTracksRuntime',
  update_target_invalid: 'updateErrorTargetInvalid',
  update_target_unsupported: 'updateCompatibilityPackageTarget',
  update_worktree_invalid: 'updateErrorWorktreeInvalid',
  update_helper_missing: 'updateErrorHelperMissing',
  update_helper_start_failed: 'updateErrorHelperFailed',
  update_check_failed: 'updateErrorCheckFailed',
  update_apply_failed: 'updateErrorApplyFailed',
  update_verification_failed: 'updateErrorVerificationFailed',
  update_restart_failed: 'updateErrorRestartFailed',
  update_state_corrupt: 'updateErrorStateCorrupt',
  update_helper_failed: 'updateErrorHelperFailed',
  update_git_failed: 'updateErrorGitFailed',
};

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
  if (value === null || value === undefined || value === '') {
    return null;
  }
  const raw = typeof value === 'number' && value < 10_000_000_000 ? value * 1000 : value;
  const date = new Date(raw);
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
  const capabilityCode = !operationActive ? status?.capabilities.reason_code : null;
  const targetCode = candidate && !candidate.compatible
    ? candidate.compatibility_code
    : !candidate
      ? status?.last_check_error_code
      : null;
  const operationCode = operation?.error_code ?? null;

  const blockerCodes = [
    !effectiveOwner ? 'update_owner_required' : capabilityCode,
    targetCode,
    operationCode,
    viewErrorKey,
  ].filter((value, index, values): value is string => Boolean(value) && values.indexOf(value) === index);
  const normalizedBlockers = blockerCodes.map(normalizeCode);
  const showBranchDetail = normalizedBlockers.includes('update_developer_branch');
  const showManifestDetail = normalizedBlockers.includes('update_manifest_missing');
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
                : blockerCodes.length > 0
                  ? styles.stateWarning
                  : styles.stateReady
            }`}>
              {operationActive
                ? t(phaseKey)
                : blockerCodes.length > 0
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

            {blockerCodes.length > 0 && (
              <div className={`${styles.notice} ${styles.errorNotice}`} role="alert">
                <InfoIcon aria-hidden="true" />
                <div className={styles.blockerContent}>
                  <strong>{t('updateErrorTitle')}</strong>
                  <ul className={styles.blockerList}>
                    {blockerCodes.map((code) => (
                      <li className={styles.blockerItem} key={code}>
                        <span>
                          {code === capabilityCode
                            ? t('updateBlockerCurrentInstallation')
                            : t('updateBlockerTarget', {
                              channel: selectedChannel === 'stable'
                                ? t('updateChannelStable')
                                : t('updateChannelLatest'),
                            })}
                        </span>
                        <small>{t(code.includes('_') ? codeKey(code) : code)}</small>
                        {showBranchDetail && normalizeCode(code) === 'update_developer_branch' && (
                          <small>
                            {t('updateBlockerBranchDetail', {
                              branch: status.current.branch || t('updateUnknown'),
                              defaultBranch: DEFAULT_UPDATE_BRANCH,
                            })}
                          </small>
                        )}
                        {showManifestDetail && normalizeCode(code) === 'update_manifest_missing' && (
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
                <div className={styles.progressTrack}>
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
