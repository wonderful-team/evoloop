// 基础输入框组件

import React, { forwardRef } from 'react';
import { View, StyleSheet, TextInput as RNTextInput } from 'react-native';
import { TextInput, TextInputProps, HelperText } from 'react-native-paper';

interface CustomInputProps extends TextInputProps {
  error?: string;
}

export const Input = forwardRef<RNTextInput, CustomInputProps>(
  ({ error, ...props }, ref) => {
    return (
      <View style={styles.container}>
        <TextInput
          ref={ref}
          {...props}
          error={!!error}
        />
        {error && (
          <HelperText type="error" visible={!!error}>
            {error}
          </HelperText>
        )}
      </View>
    );
  }
);

const styles = StyleSheet.create({
  container: {
    marginVertical: 4,
  },
});
