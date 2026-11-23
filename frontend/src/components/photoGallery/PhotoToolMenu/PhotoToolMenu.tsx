import { ArrowRightLeft, Maximize2, Pencil } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { PhotoToolsIcon, SpatialReframingIcon } from '@/components/common/Icons';
import { SelectMenu } from '@/components/common/SelectMenu';
import type { PhotoTool } from '@/types/portrait';

import styles from '@/components/photoGallery/PhotoToolMenu/PhotoToolMenu.module.css';

interface PhotoToolMenuProps {
  onSelect: (tool: PhotoTool) => void;
  current?: PhotoTool;
  disabled?: boolean;
  className?: string;
  triggerClassName?: string;
}

export function PhotoToolMenu({ onSelect, current, disabled, className, triggerClassName }: PhotoToolMenuProps) {
  const { t } = useTranslation();
  const label = t(current ? 'photoTools.continue' : 'photoTools.title');
  const options = [
    { value: 'edit', label: t('photoTools.edit'), icon: <Pencil size={16} /> },
    { value: 'extend', label: t('photoTools.extend'), icon: <Maximize2 size={16} /> },
    { value: 'reframe', label: t('portrait.title'), icon: <SpatialReframingIcon width={16} height={16} /> },
  ].filter(({ value }) => value !== current);
  return <SelectMenu portal value="" triggerLabel={label} ariaLabel={label} disabled={disabled}
    className={[styles.root, className].filter(Boolean).join(' ')} triggerClassName={triggerClassName}
    menuClassName={styles.menu} icon={current ? <ArrowRightLeft size={16} /> : <PhotoToolsIcon width={16} height={16} />}
    options={options} onChange={(tool) => { if (tool === 'edit' || tool === 'extend' || tool === 'reframe') onSelect(tool); }} />;
}
