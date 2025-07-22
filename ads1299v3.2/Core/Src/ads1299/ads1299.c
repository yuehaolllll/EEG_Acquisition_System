/* ads1299.c */
#include "ads1299.h"
#include <stdio.h>
#include "string.h"
#include "main.h"

ADS1299_Handle_t adsHandle;
extern void DWT_Delay_us(volatile uint32_t microseconds);
extern osMessageQId ads1299DataQueueHandle;

#define CS_LOW()     HAL_GPIO_WritePin(ADS1299_CS_GPIO_Port, ADS1299_CS_Pin, GPIO_PIN_RESET)
#define CS_HIGH()    HAL_GPIO_WritePin(ADS1299_CS_GPIO_Port, ADS1299_CS_Pin, GPIO_PIN_SET)

#define START_HIGH() HAL_GPIO_WritePin(ADS1299_START_GPIO_Port, ADS1299_START_Pin, GPIO_PIN_SET)
#define START_LOW()  HAL_GPIO_WritePin(ADS1299_START_GPIO_Port, ADS1299_START_Pin, GPIO_PIN_RESET)

#define RESET_HIGH() HAL_GPIO_WritePin(ADS1299_RESET_GPIO_Port, ADS1299_RESET_Pin, GPIO_PIN_SET)
#define RESET_LOW()  HAL_GPIO_WritePin(ADS1299_RESET_GPIO_Port, ADS1299_RESET_Pin, GPIO_PIN_RESET)



void ADS1299_CS_Low(void) {
    HAL_GPIO_WritePin(ADS1299_CS_GPIO_Port, ADS1299_CS_Pin, GPIO_PIN_RESET);
		DWT_Delay_us(10);
}

void ADS1299_CS_High(void) {
		DWT_Delay_us(10);
    HAL_GPIO_WritePin(ADS1299_CS_GPIO_Port, ADS1299_CS_Pin, GPIO_PIN_SET);
		DWT_Delay_us(10);
}

void ADS1299_WriteCommand(ADS1299_Handle_t *dev, uint8_t cmd) {
    ADS1299_CS_Low();
    HAL_StatusTypeDef status = HAL_SPI_Transmit(dev->hspi, &cmd, 1, 100);
    ADS1299_CS_High();
		//printf("WriteCommand: CMD=0x%02X, Status=%d\r\n", cmd, status);
}

uint8_t ADS1299_ReadRegister(ADS1299_Handle_t *dev, uint8_t reg) {
    uint8_t tx[2] = {ADS1299_CMD_RREG | reg, 0x00};
    uint8_t rx = 0;
    ADS1299_CS_Low();
    HAL_StatusTypeDef status = HAL_SPI_Transmit(dev->hspi, tx, 2, 100);
    //printf("ReadRegister: Reg=0x%02X, Transmit Status=%d\r\n", reg, status);
    status = HAL_SPI_Receive(dev->hspi, &rx, 1, 100);
    //printf("ReadRegister: Reg=0x%02X, Receive Status=%d, Value=0x%02X\r\n", reg, status, rx);
    ADS1299_CS_High();
    return rx;
}

void ADS1299_WriteRegister(ADS1299_Handle_t *dev, uint8_t reg, uint8_t value) {
    uint8_t tx[3] = {ADS1299_CMD_WREG | reg, 0x00, value};
    ADS1299_CS_Low();
    HAL_StatusTypeDef status = HAL_SPI_Transmit(dev->hspi, tx, 3, 100);
    ADS1299_CS_High();
    //printf("WriteRegister: Reg=0x%02X, Value=0x%02X, Status=%d\r\n", reg, value, status);
}


void ADS1299_Init(ADS1299_Handle_t *dev) {
		printf("ADS1299 Init Starting...\r\n");
		// 复位
    printf("Init: Step 1 - Reset sequence...\r\n");
		ADS1299_CS_High();
		START_LOW();
		RESET_LOW();
		HAL_Delay(2);
		RESET_HIGH();
		HAL_Delay(100);
		HAL_Delay(20);

		// 停止连续读取
    printf("Init: Step 2 - Sending SDATAC command...\r\n");
    ADS1299_WriteCommand(dev, ADS1299_CMD_SDATAC);
    HAL_Delay(10);

    // 读取并打印 ID 寄存器
		uint8_t id = ADS1299_ReadRegister(dev, ADS1299_REG_ID);
		printf("ADS1299 ID: 0x%02X (Expected: 0x3E)\r\n", id);
		if (id != 0x3E) {
        printf("Error: ADS1299 ID mismatch! Halting...\r\n");
        while(1);
    }				
	
/**
  * @brief  ADS1299 register config for amplification design
*/
//    printf("Init: Step 3 - Configuring registers...\r\n");
//    ADS1299_WriteRegister(dev, ADS1299_REG_CONFIG1, 0x96);  		// 500 SPS
//    ADS1299_WriteRegister(dev, ADS1299_REG_CONFIG2, 0xC0);  		// Test signal
//    ADS1299_WriteRegister(dev, ADS1299_REG_CONFIG3, 0x61);  		// Bias    
////    ADS1299_WriteRegister(dev, ADS1299_REG_LOFF, 0x00);         // no loff  		
////		ADS1299_WriteRegister(dev, ADS1299_REG_BIAS_SENSP, 0x00); 	// REFP   
////    ADS1299_WriteRegister(dev, ADS1299_REG_BIAS_SENSN, 0x00); 	// REFN

//		printf("CONFIG1 Read: 0x%02X\r\n", ADS1299_ReadRegister(dev, ADS1299_REG_CONFIG1));
//		printf("CONFIG2 Read: 0x%02X\r\n", ADS1299_ReadRegister(dev, ADS1299_REG_CONFIG2));
//		printf("CONFIG3 Read: 0x%02X\r\n", ADS1299_ReadRegister(dev, ADS1299_REG_CONFIG3));
//		printf("LOFF    Read: 0x%02X\r\n", ADS1299_ReadRegister(dev, ADS1299_REG_LOFF));
//		printf("BIAS_SENSP  : 0x%02X\r\n", ADS1299_ReadRegister(dev, ADS1299_REG_BIAS_SENSP));
//		printf("BIAS_SENSN  : 0x%02X\r\n", ADS1299_ReadRegister(dev, ADS1299_REG_BIAS_SENSN));    

//    for (uint8_t i = ADS1299_REG_CH8SET; i >= ADS1299_REG_CH1SET; i--) {
//				//if(i <= ADS1299_REG_CH4SET){
//					//ADS1299_WriteRegister(dev, i, 0x81);
//				//}else{
//					ADS1299_WriteRegister(dev, i, 0x60);
//				//}
//        
//				uint8_t val = ADS1299_ReadRegister(dev, i);
//				printf("CH%dSET: Read 0x%02X\r\n", i - ADS1299_REG_CH1SET + 1, val);
//    }
		
/**
  * @brief  ADS1299 register config for normal design
*/
    printf("Init: Step 3 - Configuring registers...\r\n");
    ADS1299_WriteRegister(dev, ADS1299_REG_CONFIG1, 0xB6);  		// enable interanl clock
    ADS1299_WriteRegister(dev, ADS1299_REG_CONFIG2, 0xC0);  		// normal input 
    ADS1299_WriteRegister(dev, ADS1299_REG_CONFIG3, 0x6C);  		// external VREF and open BIAS
		ADS1299_WriteRegister(dev, ADS1299_REG_MISC1,   0x20); 			// all Channel-N connect to SRB1
//    ADS1299_WriteRegister(dev, ADS1299_REG_LOFF, 0x00);       // no loff detect	
		ADS1299_WriteRegister(dev, ADS1299_REG_BIAS_SENSP, 0x0F); 	// 1-4 channel connect to bias-P
    ADS1299_WriteRegister(dev, ADS1299_REG_BIAS_SENSN, 0x0F); 	// 1-4 channel connect to bias-N

		printf("CONFIG1 Read: 0x%02X\r\n", ADS1299_ReadRegister(dev, ADS1299_REG_CONFIG1));
		printf("CONFIG2 Read: 0x%02X\r\n", ADS1299_ReadRegister(dev, ADS1299_REG_CONFIG2));
		printf("CONFIG3 Read: 0x%02X\r\n", ADS1299_ReadRegister(dev, ADS1299_REG_CONFIG3));
		printf("LOFF    Read: 0x%02X\r\n", ADS1299_ReadRegister(dev, ADS1299_REG_LOFF));
		printf("BIAS_SENSP  : 0x%02X\r\n", ADS1299_ReadRegister(dev, ADS1299_REG_BIAS_SENSP));
		printf("BIAS_SENSN  : 0x%02X\r\n", ADS1299_ReadRegister(dev, ADS1299_REG_BIAS_SENSN));    

    for (uint8_t i = ADS1299_REG_CH1SET; i <= ADS1299_REG_CH8SET; i++) {
				if(i <= ADS1299_REG_CH4SET){
					ADS1299_WriteRegister(dev, i, 0x60); // 0x61->input shorted      0x60->normal electrode input   0x65->test signal
				}else{
					ADS1299_WriteRegister(dev, i, 0x81); // close 
				}
        
				uint8_t val = ADS1299_ReadRegister(dev, i);
				printf("CH%dSET: Read 0x%02X\r\n", i - ADS1299_REG_CH1SET + 1, val);
    }
		
		// 开始连续读取
    printf("Init: Step 5 - Sending RDATAC command...\r\n");
    ADS1299_WriteCommand(dev, ADS1299_CMD_RDATAC);
    HAL_Delay(10);

    printf("Init: Step 6 - Sending START command...\r\n");
    START_HIGH();
    HAL_Delay(10);
    printf("Init: ADS1299 initialization completed.\r\n");
}

void ADS1299_ReadData(ADS1299_Handle_t *dev, ADS1299_Data_t *data) {
    uint8_t tx_dummy[27] = {0}; // 发送27字节的哑元数据来产生时钟
    uint8_t rx_buffer[27]; // 3 字节状态 + 8 通道 * 3 字节 = 27 字节
    
    ADS1299_CS_Low();
    // 发送哑元数据，同时接收27字节的有效数据
    HAL_StatusTypeDef status = HAL_SPI_TransmitReceive(dev->hspi, tx_dummy, rx_buffer, 27, 100);
    ADS1299_CS_High();

		//printf("SPI Read Status: %d\r\n", status);
    if (status == HAL_OK) {
//        printf("Raw SPI Data: ");
//        for (uint8_t i = 0; i < 27; i++) {
//            printf("%02X ", rx_buffer[i]);
//        }
//        printf("\r\n");

        // 复制状态字
        memcpy(data->status, rx_buffer, 3);
        // 复制 8 通道数据
        for (uint8_t i = 0; i < 8; i++) {
            memcpy(data->channel_data[i], &rx_buffer[3 + i * 3], 3);
        }
    } else {
        printf("Error: SPI read failed, status=%d\r\n", status);
    }
}




