import React from 'react';

type Props = {
  children: React.ReactNode;
  onError?: (error: Error, info: React.ErrorInfo) => void;
};

type State = { hasError: boolean };

export default class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(/* error: Error */) {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    if (this.props.onError) this.props.onError(error, info);
    // Still log for debugging
    // eslint-disable-next-line no-console
    console.error('Uncaught render error:', error, info);
  }

  render() {
    if (this.state.hasError) {
      // UI is handled by overlay via onError callback; render nothing
      return null;
    }
    return this.props.children;
  }
}
