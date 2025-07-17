/* ads1299.h */
#ifndef __ADS1299_H__
#define __ADS1299_H__

#include "stm32f4xx_hal.h"
#include "cmsis_os.h"

// === SPI and GPIO Config ===
#define ADS1299_SPI               hspi2
#define ADS1299_CS_GPIO_Port      GPIOB
#define ADS1299_CS_Pin            GPIO_PIN_12
#define ADS1299_RESET_GPIO_Port   GPIOC
#define ADS1299_RESET_Pin         GPIO_PIN_8
#define ADS1299_START_GPIO_Port   GPIOC
#define ADS1299_START_Pin         GPIO_PIN_7
#define ADS1299_DRDY_GPIO_Port    GPIOC
#define ADS1299_DRDY_Pin          GPIO_PIN_6

extern SPI_HandleTypeDef ADS1299_SPI;

// === ADS1299 Commands ===
#define ADS1299_CMD_WAKEUP        0x02
#define ADS1299_CMD_STANDBY       0x04
#define ADS1299_CMD_RESET         0x06
#define ADS1299_CMD_START         0x08
#define ADS1299_CMD_STOP          0x0A
#define ADS1299_CMD_RDATAC        0x10
#define ADS1299_CMD_SDATAC        0x11
#define ADS1299_CMD_RDATA         0x12

#define ADS1299_CMD_RREG          0x20
#define ADS1299_CMD_WREG          0x40

// === ADS1299 Register Addresses ===
#define ADS1299_REG_ID            0x00
#define ADS1299_REG_CONFIG1       0x01
#define ADS1299_REG_CONFIG2       0x02
#define ADS1299_REG_CONFIG3       0x03
#define ADS1299_REG_LOFF          0x04
#define ADS1299_REG_CH1SET        0x05
#define ADS1299_REG_CH2SET        0x06
#define ADS1299_REG_CH3SET        0x07
#define ADS1299_REG_CH4SET        0x08
#define ADS1299_REG_CH5SET        0x09
#define ADS1299_REG_CH6SET        0x0A
#define ADS1299_REG_CH7SET        0x0B
#define ADS1299_REG_CH8SET        0x0C
#define ADS1299_REG_BIAS_SENSP    0x0D
#define ADS1299_REG_BIAS_SENSN    0x0E
#define ADS1299_REG_LOFF_SENS     0x0F
#define ADS1299_REG_CONFIG4       0x17
#define ADS1299_REG_MISC1         0x15

// === Structs ===
typedef struct  {
    uint8_t status[3];
    uint8_t channel_data[8][3];
} ADS1299_Data_t;

typedef struct {
    SPI_HandleTypeDef *hspi;
    osSemaphoreId dataReadySemaphore;
} ADS1299_Handle_t;


extern ADS1299_Handle_t adsHandle;
extern osSemaphoreId ads1299Semaphore;

// === API ===
void ADS1299_Init(ADS1299_Handle_t *dev);
void ADS1299_ReadData(ADS1299_Handle_t *dev, ADS1299_Data_t *data);
uint8_t ADS1299_ReadRegister(ADS1299_Handle_t *dev, uint8_t reg);
void ADS1299_WriteRegister(ADS1299_Handle_t *dev, uint8_t reg, uint8_t value);
//void ADS1299_Task(void const *argument);


#endif /* __ADS1299_H__ */

