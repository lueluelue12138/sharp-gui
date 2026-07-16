import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  ApiError,
  applyUpdate,
  checkForUpdates,
  fetchUpdateStatus,
  getExpectedUpdateCommit,
  isActiveUpdateOperation,
  pollUpdateStatus,
  rollbackUpdate,
} from '@/api';
import { Button } from '@/components/common/Button';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import {
  CheckIcon,
  ClockIcon,
  DownloadIcon,
  InfoIcon,
  ResetIcon,
} from '@/components/common/Icons';
import type {
  UpdateAction,
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
  action: UpdateAction;
  startedInstanceId: string;
  expectedCommit: string | null;
  operationId: string | null;
}

type Confirmation =
  | { kind: 'apply'; candidate: UpdateCandidate }
  | { kind: 'rollback' }
  | null;

const PHASE_KEYS: Record<string, string> = {
  idle: 'updatePhaseIdle',
  queued: 'updatePhaseQueued',
  checking: 'updatePhaseChecking',
  resolving: 'updatePhaseResolving',
  fetching: 'updatePhaseFetching',
  downloading: 'updatePhaseDownloading',
  preparing: 'updatePhasePreparing',
  validating: 'updatePhaseValidating',
  waiting_for_server: 'updatePhaseWaitingForServer',
  stopping: 'updatePhaseStopping',
  applying: 'updatePhaseApplying',
  checking_out: 'updatePhaseCheckingOut',
  verifying: 'updatePhaseVerifying',
  restarting: 'updatePhaseRestarting',
  completed: 'updatePhaseCompleted',
  done: 'updatePhaseCompleted',
  success: 'updatePhaseCompleted',
  failed: 'updatePhaseFailed',
  rolling_back: 'updatePhaseRollingBack',
  rollback_verifying: 'updatePhaseRollbackVerifying',
  rolled_back: 'updatePhaseRolledBack',
  rollback_failed: 'updatePhaseRollbackFailed',
  cancelled: 'updatePhaseCancelled',
  ready: 'updatePhaseReady',
  checked: 'updatePhaseChecked',
  up_to_date: 'updatePhaseUpToDate',
};

const ACTION_KEYS: Record<string, string> = {
  check: 'updateActionCheck',
  apply: 'updateActionApply',
  rollback: 'updateActionRollback',
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
  'legacy-release': 'updateInstallationLegacyRelease',
  'legacy-portable': 'updateInstallationLegacyPortable',
  unknown: 'updateInstallationUnknown',
};

const CODE_KEYS: Record<string, string> = {
  owner_required: 'updateReasonOwnerRequired',
  update_owner_required: 'updateReasonOwnerRequired',
  git_unavailable: 'updateReasonGitUnavailable',
  update_git_unavailable: 'updateReasonGitUnavailable',
  update_git_too_old: 'updateCompatibilityGitTooOld',
  update_git_failed: 'updateErrorGitFailed',
  metadata_unavailable: 'updateReasonMetadataUnavailable',
  update_metadata_unavailable: 'updateReasonMetadataUnavailable',
  legacy_portable_unsupported: 'updateReasonLegacyPortable',
  update_legacy_portable_unsupported: 'updateReasonLegacyPortable',
  update_bootstrap_required: 'updateReasonLegacyPortable',
  non_default_branch: 'updateReasonNonDefaultBranch',
  update_non_default_branch: 'updateReasonNonDefaultBranch',
  update_developer_branch: 'updateReasonNonDefaultBranch',
  dirty_worktree: 'updateReasonDirtyWorktree',
  update_dirty_worktree: 'updateReasonDirtyWorktree',
  update_worktree_dirty: 'updateReasonDirtyWorktree',
  active_tasks: 'updateReasonActiveTasks',
  update_active_tasks: 'updateReasonActiveTasks',
  update_tasks_active: 'updateReasonActiveTasks',
  operation_in_progress: 'updateReasonOperationInProgress',
  update_in_progress: 'updateReasonOperationInProgress',
  runtime_revision_mismatch: 'updateCompatibilityRuntimeMismatch',
  portable_runtime_mismatch: 'updateCompatibilityRuntimeMismatch',
  update_runtime_incompatible: 'updateCompatibilityRuntimeMismatch',
  protocol_revision_mismatch: 'updateCompatibilityProtocolMismatch',
  update_protocol_incompatible: 'updateCompatibilityProtocolMismatch',
  update_protocol_mismatch: 'updateCompatibilityProtocolMismatch',
  package_target_unsupported: 'updateCompatibilityPackageTarget',
  update_package_target_unsupported: 'updateCompatibilityPackageTarget',
  frontend_dist_missing: 'updateCompatibilityFrontendMissing',
  update_frontend_missing: 'updateCompatibilityFrontendMissing',
  manifest_missing: 'updateCompatibilityManifestMissing',
  manifest_invalid: 'updateCompatibilityManifestInvalid',
  update_manifest_invalid: 'updateCompatibilityManifestInvalid',
  git_version_too_old: 'updateCompatibilityGitTooOld',
  target_untrusted: 'updateCompatibilityTargetUntrusted',
  update_target_untrusted: 'updateCompatibilityTargetUntrusted',
  update_source_untrusted: 'updateErrorSourceUntrusted',
  target_expired: 'updateErrorTargetExpired',
  update_target_expired: 'updateErrorTargetExpired',
  full_package_required: 'updateCompatibilityFullPackageRequired',
  update_full_package_required: 'updateCompatibilityFullPackageRequired',
  rollback_unavailable: 'updateReasonRollbackUnavailable',
  update_rollback_unavailable: 'updateReasonRollbackUnavailable',
  update_channel_invalid: 'updateErrorRequestInvalid',
  update_request_invalid: 'updateErrorRequestInvalid',
  update_already_current: 'updateErrorAlreadyCurrent',
  update_incompatible: 'updateCompatibilityFullPackageRequired',
  update_installation_unsupported: 'updateErrorInstallationUnsupported',
  update_installed_revision_changed: 'updateErrorRevisionChanged',
  update_interrupted_rolled_back: 'updateErrorRolledBack',
  update_not_supported: 'updateErrorNotSupported',
  update_operation_invalid: 'updateErrorOperationInvalid',
  update_recovery_required: 'updateErrorRecoveryRequired',
  update_release_invalid: 'updateErrorReleaseInvalid',
  update_release_snapshot_mismatch: 'updateErrorReleaseSnapshotMismatch',
  update_response_invalid: 'updateErrorResponseInvalid',
  update_response_too_large: 'updateErrorResponseTooLarge',
  update_server_stop_timeout: 'updateErrorServerStopTimeout',
  update_target_changed: 'updateErrorTargetChanged',
  update_target_tracks_runtime: 'updateErrorTargetTracksRuntime',
  update_target_invalid: 'updateErrorTargetInvalid',
  update_target_metadata_missing: 'updateCompatibilityManifestMissing',
  update_target_unsupported: 'updateCompatibilityPackageTarget',
  update_worktree_invalid: 'updateErrorWorktreeInvalid',
  update_helper_missing: 'updateErrorHelperMissing',
  update_helper_start_failed: 'updateErrorHelperFailed',
  compatible: 'updateCompatibilityCompatible',
  update_compatible: 'updateCompatibilityCompatible',
  check_failed: 'updateErrorCheckFailed',
  update_check_failed: 'updateErrorCheckFailed',
  rate_limited: 'updateErrorRateLimited',
  update_rate_limited: 'updateErrorRateLimited',
  update_check_rate_limited: 'updateErrorRateLimited',
  network_error: 'updateErrorNetwork',
  update_network_error: 'updateErrorNetwork',
  tls_error: 'updateErrorTls',
  update_tls_error: 'updateErrorTls',
  apply_failed: 'updateErrorApplyFailed',
  update_apply_failed: 'updateErrorApplyFailed',
  verification_failed: 'updateErrorVerificationFailed',
  update_verification_failed: 'updateErrorVerificationFailed',
  rolled_back: 'updateErrorRolledBack',
  update_rolled_back: 'updateErrorRolledBack',
  rollback_failed: 'updateErrorRollbackFailed',
  update_rollback_failed: 'updateErrorRollbackFailed',
  restart_failed: 'updateErrorRestartFailed',
  update_restart_failed: 'updateErrorRestartFailed',
  state_corrupt: 'updateErrorStateCorrupt',
  update_state_corrupt: 'updateErrorStateCorrupt',
  helper_failed: 'updateErrorHelperFailed',
  update_helper_failed: 'updateErrorHelperFailed',
};

const FAILURE_PHASES = new Set(['cancelled', 'failed', 'rollback_failed']);

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

function isTimestampExpired(value: UpdateTimestamp | undefined): boolean {
  if (value === null || value === undefined || value === '') {
    return false;
  }
  const raw = typeof value === 'number' && value < 10_000_000_000 ? value * 1000 : value;
  const timestamp = new Date(raw).getTime();
  return !Number.isNaN(timestamp) && timestamp <= Date.now();
}

function commitsMatch(left?: string | null, right?: string | null): boolean {
  if (!left || !right) {
    return false;
  }
  const normalizedLeft = left.toLowerCase();
  const normalizedRight = right.toLowerCase();
  return normalizedLeft === normalizedRight
    || normalizedLeft.startsWith(normalizedRight)
    || normalizedRight.startsWith(normalizedLeft);
}

function isDowngrade(candidate?: UpdateCandidate | null): boolean {
  return candidate?.relation === 'behind' || candidate?.relation === 'downgrade';
}

function isTransientMutationError(error: unknown): boolean {
  return !(error instanceof ApiError);
}

export function UpdateSettingsSection({ active, isOwner }: UpdateSettingsSectionProps) {
  const { t, i18n } = useTranslation();
  const [status, setStatus] = useState<UpdateStatusResponse | null>(null);
  const [selectedChannel, setSelectedChannel] = useState<UpdateChannel>('stable');
  const [isLoading, setIsLoading] = useState(false);
  const [busyAction, setBusyAction] = useState<UpdateAction | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation>(null);
  const [viewErrorKey, setViewErrorKey] = useState<string | null>(null);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [tracker, setTracker] = useState<OperationTracker | null>(null);
  const reloadStartedRef = useRef(false);

  const selectedCandidate = status?.channels[selectedChannel] ?? null;
  const operation = status?.operation ?? null;
  const operationIsActive = isActiveUpdateOperation(operation);
  const effectiveOwner = isOwner && (status?.is_owner ?? true);
  const actionsLocked = Boolean(busyAction || operationIsActive || tracker);
  const updateUnavailable = !effectiveOwner
    || Boolean(status?.capabilities.reason_code && !status.capabilities.can_apply);
  const candidateExpired = Boolean(
    selectedCandidate?.update_available && isTimestampExpired(selectedCandidate.expires_at),
  );
  const canCheck = effectiveOwner && Boolean(status?.capabilities.can_check);
  const canApply = effectiveOwner
    && !candidateExpired
    && Boolean(status?.capabilities.can_apply)
    && Boolean(selectedCandidate?.update_available)
    && Boolean(selectedCandidate?.compatible)
    && Boolean(selectedCandidate?.target_token);
  const canRollback = effectiveOwner
    && Boolean(status?.capabilities.can_rollback);

  const operationErrorKey = operation?.error_code ? codeKey(operation.error_code) : null;
  const cachedCheckErrorKey = selectedCandidate?.check_error_code
    ? codeKey(selectedCandidate.check_error_code)
    : null;
  const lastCheckErrorKey = !selectedCandidate && status?.last_check_error_code
    ? codeKey(status.last_check_error_code)
    : null;
  const visibleErrorKey = viewErrorKey
    ?? operationErrorKey
    ?? lastCheckErrorKey
    ?? (candidateExpired ? 'updateErrorTargetExpired' : null);
  const checkedAt = formatTimestamp(
    selectedCandidate?.checked_at ?? status?.checked_at ?? null,
    i18n.resolvedLanguage ?? i18n.language,
  );

  const versionRows = useMemo(() => {
    if (!status) {
      return [];
    }
    const installationKey = INSTALLATION_KEYS[normalizeCode(status.current.installation_kind)]
      ?? 'updateInstallationUnknown';
    return [
      { label: t('updateInstalledVersion'), value: status.current.display_version || t('updateUnknown') },
      {
        label: t('updateCurrentCommit'),
        value: status.current.short_commit || status.current.commit || t('updateUnknown'),
        mono: true,
      },
      {
        label: t('updateInstalledChannel'),
        value: status.current.channel === 'stable'
          ? t('updateChannelStable')
          : status.current.channel === 'latest'
            ? t('updateChannelLatest')
            : t('updateUnknown'),
      },
      { label: t('updateInstallation'), value: t(installationKey) },
      { label: t('updateBranch'), value: status.current.branch || t('updateUnknown'), mono: true },
    ];
  }, [status, t]);

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
        const installedChannel = nextStatus.current.channel;
        if (installedChannel === 'stable' || installedChannel === 'latest') {
          setSelectedChannel(installedChannel);
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setViewErrorKey(error instanceof ApiError
          ? apiErrorKey(error, 'updateErrorStatusFailed')
          : 'updateErrorStatusFailed');
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      });

    return () => controller.abort();
  }, [active]);

  const activeOperationId = operationIsActive ? operation?.id ?? null : null;

  useEffect(() => {
    if (!active || !status || (!activeOperationId && !tracker)) {
      return undefined;
    }

    const controller = new AbortController();
    const initialStatus = status;
    const initialOperationId = initialStatus.operation?.id ?? null;
    const action = tracker?.action ?? normalizeCode(initialStatus.operation?.action) as UpdateAction;
    const startedInstanceId = tracker?.startedInstanceId ?? initialStatus.server_instance_id;
    let expectedCommit = tracker?.expectedCommit ?? getExpectedUpdateCommit(initialStatus.operation);
    let operationSeen = isActiveUpdateOperation(initialStatus.operation);

    const shouldReload = (nextStatus: UpdateStatusResponse): boolean => {
      const instanceChanged = Boolean(
        startedInstanceId && nextStatus.server_instance_id !== startedInstanceId,
      );
      const targetReached = commitsMatch(nextStatus.current.commit, expectedCommit);
      if (
        (action === 'apply' || action === 'rollback')
        && instanceChanged
        && targetReached
        && !reloadStartedRef.current
      ) {
        reloadStartedRef.current = true;
        window.location.reload();
        return true;
      }
      return false;
    };

    setIsReconnecting(false);
    pollUpdateStatus({
      initialStatus,
      signal: controller.signal,
      onStatus: (nextStatus) => {
        setStatus(nextStatus);
        setIsReconnecting(false);
        expectedCommit ||= getExpectedUpdateCommit(nextStatus.operation);
        if (
          isActiveUpdateOperation(nextStatus.operation)
          || Boolean(nextStatus.operation?.id && nextStatus.operation.id !== initialOperationId)
        ) {
          operationSeen = true;
        }
      },
      onTransientError: () => {
        if (action === 'apply' || action === 'rollback') {
          setIsReconnecting(true);
        }
      },
      shouldStop: (nextStatus) => {
        if (shouldReload(nextStatus)) {
          return true;
        }

        if (isActiveUpdateOperation(nextStatus.operation)) {
          return false;
        }
        if (!operationSeen) {
          return false;
        }

        const phase = normalizeCode(nextStatus.operation?.phase);
        if (
          FAILURE_PHASES.has(phase)
          || nextStatus.operation?.error_code
          || (phase === 'rolled_back' && action === 'apply')
        ) {
          return true;
        }
        if (action === 'apply' || action === 'rollback') {
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
        if (controller.signal.aborted) {
          return;
        }
        setTracker(null);
        setIsReconnecting(false);
        setViewErrorKey(error instanceof ApiError ? codeKey(error.data?.code) : 'updateReconnectTimeout');
      });

    return () => controller.abort();
    // Phase/progress updates are consumed by the poll callback. Restart only for a new operation/tracker.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, activeOperationId, tracker?.token]);

  const startTracker = (
    action: UpdateAction,
    startedInstanceId: string,
    expectedCommit: string | null,
    operationId: string | null,
  ) => {
    setTracker({
      token: Date.now(),
      action,
      startedInstanceId,
      expectedCommit,
      operationId,
    });
  };

  const handleCheck = async () => {
    if (!status || !canCheck || actionsLocked) {
      return;
    }
    setBusyAction('check');
    setViewErrorKey(null);
    try {
      const nextStatus = await checkForUpdates(selectedChannel);
      setStatus(nextStatus);
      if (isActiveUpdateOperation(nextStatus.operation)) {
        startTracker(
          'check',
          status.server_instance_id,
          getExpectedUpdateCommit(nextStatus.operation),
          nextStatus.operation?.id ?? null,
        );
      }
    } catch (error) {
      setViewErrorKey(error instanceof ApiError
        ? apiErrorKey(error, 'updateErrorCheckFailed')
        : 'updateErrorCheckFailed');
    } finally {
      setBusyAction(null);
    }
  };

  const handleStatusRetry = async () => {
    setIsLoading(true);
    setViewErrorKey(null);
    try {
      const nextStatus = await fetchUpdateStatus();
      setStatus(nextStatus);
      const installedChannel = nextStatus.current.channel;
      if (installedChannel === 'stable' || installedChannel === 'latest') {
        setSelectedChannel(installedChannel);
      }
    } catch (error) {
      setViewErrorKey(error instanceof ApiError
        ? apiErrorKey(error, 'updateErrorStatusFailed')
        : 'updateErrorStatusFailed');
    } finally {
      setIsLoading(false);
    }
  };

  const runApply = async (candidate: UpdateCandidate) => {
    if (!status || !effectiveOwner || actionsLocked || !candidate.target_token) {
      return;
    }

    const startedInstanceId = status.server_instance_id;
    setBusyAction('apply');
    setViewErrorKey(null);
    try {
      const nextStatus = await applyUpdate({
        channel: candidate.channel,
        target_token: candidate.target_token,
      });
      setStatus(nextStatus);
      const phase = normalizeCode(nextStatus.operation?.phase);
      if (!FAILURE_PHASES.has(phase) && !nextStatus.operation?.error_code) {
        startTracker(
          'apply',
          startedInstanceId,
          candidate.target_sha || getExpectedUpdateCommit(nextStatus.operation),
          nextStatus.operation?.id ?? null,
        );
      }
      setConfirmation(null);
    } catch (error) {
      if (isTransientMutationError(error)) {
        startTracker('apply', startedInstanceId, candidate.target_sha, null);
        setIsReconnecting(true);
        setConfirmation(null);
      } else if (error instanceof ApiError) {
        setViewErrorKey(apiErrorKey(error, 'updateErrorApplyFailed'));
      }
    } finally {
      setBusyAction(null);
    }
  };

  const runRollback = async () => {
    if (!status || !effectiveOwner || actionsLocked) {
      return;
    }

    const startedInstanceId = status.server_instance_id;
    setBusyAction('rollback');
    setViewErrorKey(null);
    try {
      const nextStatus = await rollbackUpdate();
      setStatus(nextStatus);
      const phase = normalizeCode(nextStatus.operation?.phase);
      if (!FAILURE_PHASES.has(phase) && !nextStatus.operation?.error_code) {
        startTracker(
          'rollback',
          startedInstanceId,
          getExpectedUpdateCommit(nextStatus.operation),
          nextStatus.operation?.id ?? null,
        );
      }
      setConfirmation(null);
    } catch (error) {
      if (isTransientMutationError(error)) {
        startTracker(
          'rollback',
          startedInstanceId,
          getExpectedUpdateCommit(status.operation),
          null,
        );
        setIsReconnecting(true);
        setConfirmation(null);
      } else if (error instanceof ApiError) {
        setViewErrorKey(apiErrorKey(error, 'updateErrorRollbackFailed'));
      }
    } finally {
      setBusyAction(null);
    }
  };

  const confirmTitle = confirmation?.kind === 'rollback'
    ? t('updateRollbackTitle')
    : t('updateConfirmTitle');
  const confirmMessage = confirmation?.kind === 'rollback'
    ? t('updateRollbackMessage')
    : confirmation?.candidate.channel === 'latest'
      ? t('updateConfirmLatest', { version: confirmation.candidate.display_version })
      : isDowngrade(confirmation?.candidate)
        ? t('updateConfirmDowngrade', { version: confirmation?.candidate.display_version ?? '' })
        : t('updateConfirmStable', { version: confirmation?.candidate.display_version ?? '' });

  const progress = operation?.progress === null || operation?.progress === undefined
    ? null
    : Math.min(100, Math.max(0, operation.progress));
  const phaseKey = PHASE_KEYS[normalizeCode(operation?.phase)] ?? 'updatePhaseWorking';
  const actionKey = ACTION_KEYS[normalizeCode(operation?.action)] ?? 'updateActionUpdate';
  const relationKey = RELATION_KEYS[normalizeCode(selectedCandidate?.relation)] ?? 'updateRelationUnknown';

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
            <span className={`${styles.stateBadge} ${operationIsActive ? styles.stateBusy : updateUnavailable ? styles.stateWarning : styles.stateReady}`}>
              {operationIsActive
                ? t(phaseKey)
                : updateUnavailable
                  ? t('updateUnavailable')
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
              {versionRows.map((row) => (
                <div className={styles.versionRow} key={row.label}>
                  <dt>{row.label}</dt>
                  <dd className={row.mono ? styles.mono : undefined}>{row.value}</dd>
                </div>
              ))}
            </dl>

            {status.current.dirty && (
              <div className={`${styles.notice} ${styles.warningNotice}`} role="note">
                <InfoIcon aria-hidden="true" />
                <div>
                  <strong>{t('updateDirty')}</strong>
                  <p>{t('updateDirtyHint')}</p>
                </div>
              </div>
            )}

            <div className={styles.channelBlock}>
              <div className={styles.blockHeading}>
                <span>{t('updateChannel')}</span>
                <span>{checkedAt ? t('updateLastChecked', { time: checkedAt }) : t('updateNeverChecked')}</span>
              </div>
              <div className={styles.channelSelector} role="group" aria-label={t('updateChannel')}>
                {(['stable', 'latest'] as const).map((channel) => (
                  <button
                    key={channel}
                    type="button"
                    className={`${styles.channelButton} ${selectedChannel === channel ? styles.channelButtonSelected : ''}`}
                    aria-pressed={selectedChannel === channel}
                    onClick={() => {
                      setSelectedChannel(channel);
                      setViewErrorKey(null);
                    }}
                    disabled={actionsLocked}
                  >
                    <span>{channel === 'stable' ? t('updateChannelStable') : t('updateChannelLatest')}</span>
                    <small>{channel === 'stable' ? t('updateStableDescription') : t('updateLatestDescription')}</small>
                  </button>
                ))}
              </div>
            </div>

            {selectedChannel === 'latest' && (
              <div className={`${styles.notice} ${styles.riskNotice}`} role="note">
                <InfoIcon aria-hidden="true" />
                <div>
                  <strong>{t('updateLatestRiskTitle')}</strong>
                  <p>{t('updateLatestRisk')}</p>
                </div>
              </div>
            )}

            <div className={styles.candidateCard}>
              <div className={styles.candidateHeader}>
                <div>
                  <span className={styles.eyebrow}>{t('updateTargetVersion')}</span>
                  <strong>{selectedCandidate?.display_version ?? t('updateNotChecked')}</strong>
                </div>
                {selectedCandidate && (
                  <span className={`${styles.stateBadge} ${selectedCandidate.compatible ? styles.stateReady : styles.stateWarning}`}>
                    {selectedCandidate.compatible ? t('updateCompatible') : t('updateIncompatible')}
                  </span>
                )}
              </div>

              {selectedCandidate ? (
                <dl className={styles.candidateDetails}>
                  <div>
                    <dt>{t('updateTargetCommit')}</dt>
                    <dd className={styles.mono}>{selectedCandidate.short_sha || selectedCandidate.target_sha}</dd>
                  </div>
                  <div>
                    <dt>{t('updateRelation')}</dt>
                    <dd>{t(relationKey)}</dd>
                  </div>
                  <div>
                    <dt>{t('updateAvailability')}</dt>
                    <dd>{selectedCandidate.update_available ? t('updateAvailable') : t('updateUpToDate')}</dd>
                  </div>
                  {selectedCandidate.commits_ahead !== null && (
                    <div>
                      <dt>{t('updateCommitDistance')}</dt>
                      <dd>{t('updateCommitsAhead', { count: selectedCandidate.commits_ahead })}</dd>
                    </div>
                  )}
                </dl>
              ) : (
                <p className={styles.emptyHint}>{t('updateCheckHint')}</p>
              )}

              {selectedCandidate?.cached && (
                <span className={styles.cachedLabel}>{t('updateCachedResult')}</span>
              )}
              {cachedCheckErrorKey && (
                <p className={styles.compatibilityMessage}>
                  {t('updateCachedCheckWarning')} {t(cachedCheckErrorKey)}
                </p>
              )}
              {selectedCandidate && !selectedCandidate.compatible && (
                <p className={styles.compatibilityMessage}>
                  {t(codeKey(selectedCandidate.compatibility_code))}
                </p>
              )}
              {selectedCandidate?.release_url && (
                <a
                  className={styles.releaseLink}
                  href={selectedCandidate.release_url}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  {t('updateReleaseNotes')}
                </a>
              )}
            </div>

            {(operation || tracker || isReconnecting) && (
              <div className={styles.operationPanel} role="status" aria-live="polite">
                <div className={styles.operationHeader}>
                  <div>
                    <span className={styles.eyebrow}>{t('updateOperationTitle')}</span>
                    <strong>{t(actionKey)} · {isReconnecting ? t('updateReconnecting') : t(phaseKey)}</strong>
                  </div>
                  {progress !== null && <span>{Math.round(progress)}%</span>}
                </div>
                <div
                  className={styles.progressTrack}
                  role="progressbar"
                  aria-label={t('updateProgress')}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={progress ?? undefined}
                  aria-valuetext={progress === null ? t(phaseKey) : undefined}
                >
                  <span
                    className={`${styles.progressFill} ${progress === null ? styles.progressIndeterminate : ''}`}
                    style={progress === null ? undefined : { width: `${progress}%` }}
                  />
                </div>
                {isReconnecting && <p>{t('updateConnectionInterruptedHint')}</p>}
              </div>
            )}

            {operation?.rolled_back && (
              <div className={`${styles.notice} ${styles.successNotice}`} role="status">
                <CheckIcon aria-hidden="true" />
                <div>
                  <strong>{t('updateAutomaticRollbackTitle')}</strong>
                  <p>{t('updateAutomaticRollbackComplete')}</p>
                </div>
              </div>
            )}

            {!effectiveOwner && (
              <div className={`${styles.notice} ${styles.infoNotice}`} role="note">
                <InfoIcon aria-hidden="true" />
                <p>{t('updateOwnerOnly')}</p>
              </div>
            )}

            {effectiveOwner && status.capabilities.reason_code && (
              <div className={`${styles.notice} ${styles.infoNotice}`} role="note">
                <InfoIcon aria-hidden="true" />
                <p>{t(codeKey(status.capabilities.reason_code))}</p>
              </div>
            )}

            {visibleErrorKey && (
              <div className={`${styles.notice} ${styles.errorNotice}`} role="alert">
                <InfoIcon aria-hidden="true" />
                <div>
                  <strong>{t('updateErrorTitle')}</strong>
                  <p>{t(visibleErrorKey)}</p>
                </div>
              </div>
            )}

            <div className={styles.actions}>
              <Button
                type="button"
                variant="secondary"
                icon={<ResetIcon />}
                onClick={handleCheck}
                disabled={!canCheck || actionsLocked}
              >
                {busyAction === 'check' ? t('updateChecking') : visibleErrorKey ? t('updateRetry') : t('updateCheck')}
              </Button>
              <Button
                type="button"
                icon={<DownloadIcon />}
                onClick={() => selectedCandidate && setConfirmation({ kind: 'apply', candidate: selectedCandidate })}
                disabled={!canApply || actionsLocked}
              >
                {selectedChannel === 'latest'
                  ? t('updateApplyLatest')
                  : isDowngrade(selectedCandidate)
                    ? t('updateSwitchStable')
                    : t('updateApply')}
              </Button>
              {(status.capabilities.can_rollback || operation?.rollback_available) && (
                <Button
                  type="button"
                  variant="ghost"
                  icon={<ClockIcon />}
                  onClick={() => setConfirmation({ kind: 'rollback' })}
                  disabled={!canRollback || actionsLocked}
                >
                  {t('updateRollback')}
                </Button>
              )}
            </div>
          </>
        ) : (
          <div className={styles.statusFailure}>
            <div className={`${styles.notice} ${styles.errorNotice}`} role="alert">
              <InfoIcon aria-hidden="true" />
              <div>
                <strong>{t('updateErrorTitle')}</strong>
                <p>{t(viewErrorKey ?? 'updateErrorStatusFailed')}</p>
              </div>
            </div>
            <Button
              type="button"
              variant="secondary"
              icon={<ResetIcon />}
              onClick={() => void handleStatusRetry()}
              disabled={isLoading}
            >
              {t('updateRetry')}
            </Button>
          </div>
        )}
      </div>

      <ConfirmDialog
        isOpen={Boolean(confirmation)}
        title={confirmTitle}
        message={confirmMessage}
        confirmLabel={confirmation?.kind === 'rollback' ? t('updateConfirmRollback') : t('updateConfirmApply')}
        isBusy={busyAction === 'apply' || busyAction === 'rollback'}
        danger={
          confirmation?.kind === 'rollback'
          || isDowngrade(confirmation?.candidate)
        }
        onClose={() => !busyAction && setConfirmation(null)}
        onConfirm={() => {
          if (confirmation?.kind === 'rollback') {
            void runRollback();
          } else if (confirmation?.kind === 'apply') {
            void runApply(confirmation.candidate);
          }
        }}
      />
    </section>
  );
}
