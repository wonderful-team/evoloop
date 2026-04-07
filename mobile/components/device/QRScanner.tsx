// 二维码扫描组件

import React, { useState, useEffect } from 'react';
import { View, StyleSheet, Dimensions } from 'react-native';
import { Text, Button, Portal, Modal } from 'react-native-paper';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { MaterialIcons } from '@expo/vector-icons';

interface QRScannerProps {
  visible: boolean;
  onClose: () => void;
  onScan: (data: string) => void;
}

const { width } = Dimensions.get('window');
const scannerSize = width * 0.7;

export function QRScanner({ visible, onClose, onScan }: QRScannerProps) {
  const [permission, requestPermission] = useCameraPermissions();
  const [scanned, setScanned] = useState(false);

  useEffect(() => {
    if (visible) {
      setScanned(false);
    }
  }, [visible]);

  const handleBarCodeScanned = ({ data }: { data: string }) => {
    if (!scanned) {
      setScanned(true);
      onScan(data);
    }
  };

  if (!permission) {
    return null;
  }

  if (!permission.granted) {
    return (
      <Portal>
        <Modal
          visible={visible}
          onDismiss={onClose}
          contentContainerStyle={styles.permissionContainer}
        >
          <MaterialIcons name="camera-alt" size={64} color="#666" />
          <Text variant="titleLarge" style={styles.permissionTitle}>
            需要相机权限
          </Text>
          <Text variant="bodyMedium" style={styles.permissionText}>
            请授予相机权限以扫描二维码绑定设备
          </Text>
          <Button
            mode="contained"
            onPress={requestPermission}
            style={styles.permissionButton}
          >
            授予权限
          </Button>
          <Button onPress={onClose} style={styles.cancelButton}>
            取消
          </Button>
        </Modal>
      </Portal>
    );
  }

  return (
    <Portal>
      <Modal
        visible={visible}
        onDismiss={onClose}
        contentContainerStyle={styles.container}
      >
        <View style={styles.cameraContainer}>
          <CameraView
            style={styles.camera}
            facing="back"
            onBarcodeScanned={scanned ? undefined : handleBarCodeScanned}
            barcodeScannerSettings={{
              barcodeTypes: ['qr'],
            }}
          >
            <View style={styles.overlay}>
              <View style={styles.scanArea}>
                <View style={[styles.corner, styles.topLeft]} />
                <View style={[styles.corner, styles.topRight]} />
                <View style={[styles.corner, styles.bottomLeft]} />
                <View style={[styles.corner, styles.bottomRight]} />
              </View>
            </View>
          </CameraView>
        </View>

        <View style={styles.footer}>
          <Text variant="bodyMedium" style={styles.hint}>
            将二维码放入框内扫描
          </Text>
          <Button onPress={onClose} textColor="#fff">
            取消
          </Button>
        </View>
      </Modal>
    </Portal>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000',
    margin: 0,
  },
  cameraContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  camera: {
    width: '100%',
    height: '100%',
  },
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  scanArea: {
    width: scannerSize,
    height: scannerSize,
    backgroundColor: 'transparent',
    position: 'relative',
  },
  corner: {
    position: 'absolute',
    width: 40,
    height: 40,
    borderColor: '#00C853',
    borderWidth: 4,
  },
  topLeft: {
    top: 0,
    left: 0,
    borderRightWidth: 0,
    borderBottomWidth: 0,
  },
  topRight: {
    top: 0,
    right: 0,
    borderLeftWidth: 0,
    borderBottomWidth: 0,
  },
  bottomLeft: {
    bottom: 0,
    left: 0,
    borderRightWidth: 0,
    borderTopWidth: 0,
  },
  bottomRight: {
    bottom: 0,
    right: 0,
    borderLeftWidth: 0,
    borderTopWidth: 0,
  },
  footer: {
    padding: 24,
    alignItems: 'center',
  },
  hint: {
    color: '#fff',
    marginBottom: 16,
  },
  permissionContainer: {
    backgroundColor: '#fff',
    padding: 24,
    margin: 24,
    borderRadius: 12,
    alignItems: 'center',
  },
  permissionTitle: {
    marginTop: 16,
    marginBottom: 8,
  },
  permissionText: {
    textAlign: 'center',
    marginBottom: 24,
    opacity: 0.7,
  },
  permissionButton: {
    minWidth: 200,
    marginBottom: 8,
  },
  cancelButton: {
    minWidth: 200,
  },
});
