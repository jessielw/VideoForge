import React from 'react';
import { useOverlay } from '../context/OverlayContext';
import BlockingOverlay from './UI/BlockingOverlay';

export default function GlobalOverlay(): JSX.Element {
  const { state, hide } = useOverlay();

  return (
    <BlockingOverlay
      visible={state.visible}
      message={state.message}
      type={state.type}
      dismissible={state.dismissible}
      onDismiss={hide}
    >
      {state.customContent}
    </BlockingOverlay>
  );
}
