import { useEffect, useState } from 'react';

import { Download, Workflow } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { downloadVisualWorkflow, getVisualWorkflow } from '@/api/portrait';
import { Button } from '@/components/common/Button';
import { Modal } from '@/components/common/Modal';
import type { VisualWorkflowDependencies, VisualWorkflowName } from '@/types/portrait';

import styles from '@/components/portrait/WorkflowInfo/WorkflowInfo.module.css';

function DependencyList({ heading, entries }: { heading: string; entries: string[] }) {
  return <section className={styles.dependencies}>
    <h4>{heading}</h4>
    <ul>{entries.map((entry) => <li key={entry}>{entry}</li>)}</ul>
  </section>;
}

export function WorkflowInfo({ workflow, title }: { workflow: VisualWorkflowName; title: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<VisualWorkflowDependencies>();
  const [loadFailed, setLoadFailed] = useState(false);
  const [downloadFailed, setDownloadFailed] = useState(false);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (!open) return;
    const request = new AbortController();
    void getVisualWorkflow(workflow, request.signal).then((details) => {
      if (!request.signal.aborted) setData(details);
    }).catch(() => {
      if (!request.signal.aborted) setLoadFailed(true);
    });
    return () => request.abort();
  }, [open, workflow]);

  async function download() {
    setDownloading(true);
    setDownloadFailed(false);
    try {
      await downloadVisualWorkflow(workflow);
    } catch {
      setDownloadFailed(true);
    } finally {
      setDownloading(false);
    }
  }

  return <>
    <Button variant="ghost" size="sm" type="button" icon={<Workflow size={16} />} onClick={() => {
      setLoadFailed(false);
      setDownloadFailed(false);
      setOpen(true);
    }}>{t('portrait.visualWorkflow.view')}</Button>
    {open && <Modal portal size="lg" isOpen onClose={() => setOpen(false)}
      title={t('portrait.visualWorkflow.title', { title })}>
      <div className={styles.content}>
        <p>{t('portrait.visualWorkflow.description')}</p>
        <Button type="button" size="sm" icon={<Download size={16} />} disabled={downloading} onClick={() => void download()}>
          {t('portrait.visualWorkflow.download')}
        </Button>
        {downloadFailed && <p role="alert">{t('portrait.visualWorkflow.downloadError')}</p>}
        {loadFailed && <p role="alert">{t('portrait.visualWorkflow.loadError')}</p>}
        {!data && !loadFailed && <p role="status">{t('loading')}</p>}
        {data && <>
          <DependencyList heading={t('portrait.visualWorkflow.extensions')} entries={data.extensions} />
          <DependencyList heading={t('portrait.visualWorkflow.models')} entries={data.models} />
          <DependencyList heading={t('portrait.visualWorkflow.optimizerModels')} entries={data.optimizer_models} />
          <details className={styles.nodes}>
            <summary>{t('portrait.visualWorkflow.nodes', { count: data.nodes.length })}</summary>
            <ul>{data.nodes.map((node) => <li key={node}>{node}</li>)}</ul>
          </details>
        </>}
      </div>
    </Modal>}
  </>;
}
