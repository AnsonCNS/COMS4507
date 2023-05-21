# -*- coding: utf-8 -*-
"""LSTM_Trading_Bot.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1Euxs64Xg3BH3s6aN_l0vgjbEBeFK_9Fn
"""

import os
import uuid
import numpy as np
import random
import requests
import time
import pandas as pd
from enum import Enum
from prophet import Prophet
from datetime import date, datetime, timedelta

import matplotlib.pyplot as plt
from sklearn.preprocessing import MinMaxScaler

import IPython
from IPython.display import display, HTML, Javascript

from tensorflow.keras import Sequential
from tensorflow.keras.layers import Dense, LSTM, Dropout

# Constants
INITIAL_BALANCE = 1000000  # $1 million
INTERVALS = 5  # seconds
MINIMUM_GROWTH = 0.02  # minimum 2% increase in predicted price to trigger buy
STOP_LOSS_PERCENTAGE = 0.05  # limit loss to 5%
GOAL = 1200000  # $1.2 million

""" LSTM Prediction Functions """
def preprocess_data(data_url):
    df = pd.read_csv(data_url)
    df = df.drop(['Adj Close'], axis=1)
    #df.rename(columns={'Date': 'ds', 'Close': 'y'}, inplace=True)
    return df


def train_lstm_model(x_train):
    #Initialize the RNN
    model = Sequential() 
    model.add(LSTM(units = 50, 
                   activation = 'relu', 
                   return_sequences = True, 
                   input_shape = (x_train.shape[1], 5)))

    model.add(Dropout(0.2)) 
    model.add(LSTM(units = 60, activation = 'relu', return_sequences = True))
    model.add(Dropout(0.3)) 
    model.add(LSTM(units = 80, activation = 'relu', return_sequences = True))

    model.add(Dropout(0.4)) 
    model.add(LSTM(units = 120, activation = 'relu'))
    model.add(Dropout(0.5)) 
    model.add(Dense(units =1))
    model.summary()

    model.compile(optimizer = 'adam', loss = 'mean_squared_error')
    return model

def display_training_validation_loss(history):                      
    loss = history.history['loss']
    val_loss = history.history['val_loss']
    epochs = range(len(loss))
    plt.figure()
    plt.plot(epochs, loss, 'b', label='Training loss')
    plt.plot(epochs, val_loss, 'r', label='Validation loss')
    plt.title("Training and Validation Loss")
    plt.legend()
    plt.show()

def predict_lstm_price(model, data_test, data, days, scaler):
    # Prepare input data for prediction
    last_60_days = data_test.tail(60)  # Take the most recent 60 data points
    last_60_days = last_60_days.drop(['Date'], axis = 1)
    inputs = scaler.transform(last_60_days)  # Scale the input data
    reshaped_inputs = np.reshape(inputs, (1, 60, 5))  # Reshape the input data

    # Obtain the scaling parameters
    price_min = data['Close'].min()
    price_max = data['Close'].max()
    print("Min", price_min, "Max", price_max)

    # Reverse the scaling transformation
    predicted_price = model.predict(reshaped_inputs)
    predicted_price_rescaled = predicted_price * (price_max - price_min) + price_min
    next_day_date = days.iloc[-1]
    return predicted_price_rescaled
    # # Print the real predicted price for the next day
    # print("Predicted price for next day:", predicted_price)
    # print("Real predicted price for the next day:", next_day_date, ":", predicted_price_rescaled)


class BitcoinTransaction:
    def __init__(
        self,
        transaction_type,
        price,
        amount,
        volume,
        profit_or_loss=None,
        transaction_trigger=None,
    ):
        self.transaction_type = transaction_type
        self.price = price
        self.amount = amount
        self.volume = volume
        self.profit_or_loss = profit_or_loss
        self.transaction_trigger = transaction_trigger
        self.transaction_id = uuid.uuid4()

    def __str__(self):
        return f"Transaction ID: {self.transaction_id}, Transaction Type: {self.transaction_type}, Price: {self.price}, Amount: {self.amount} BTC, Volume: {self.volume}, Profit/Loss: {self.profit_or_loss}, Transaction Trigger: {self.transaction_trigger}"

    def __repr__(self):
        return f"({str(self)})"


class TransactionTypes(Enum):
    BUY = 1
    SELL = 2


""" Trading Bot Functions """


def get_price():
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {"X-CMC_PRO_API_KEY": "f16d5846-68ea-4cbc-88c2-b2b0ae91ae25"}
    params = {"symbol": "BTC"}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        return data["data"]["BTC"]["quote"]["USD"]["price"]
    else:
        return None


def take_decision(current_price, predicted_price, balance, buy_order, sell_order):
    # no buy orders placed yet
    if buy_order is None:
        # Check if price is predicted to grow beyond minimum required growth
        if predicted_price >= current_price * (1 + MINIMUM_GROWTH):
            # Check if we have sufficient balance
            if balance > 0:
                # Calculate the volume of BTC we can buy with our balance and the dollar amount
                volume = balance / current_price
                amount = balance
                # Place the buy order
                trigger = "Predicted future growth"
                buy_order = BitcoinTransaction(
                    TransactionTypes.BUY, current_price, amount, volume, trigger
                )
                print("New buy order placed:", buy_order)
                balance -= amount
            else:
                print("Insufficient balance to place a new buy order")
        else:
            print(
                f"Predicted future price does not meet the minimum growth requirement ({MINIMUM_GROWTH * 100}%) for buy trigger"
            )
    elif sell_order is None:
        # Check if current price has fallen to trigger stoploss sell, minimize loss
        if current_price <= buy_order.price * (1 - STOP_LOSS_PERCENTAGE):
            volume = buy_order.volume
            amount = current_price * volume
            # calculate the loss (negative profit) incurred in this sell order
            profit_or_loss = volume * (current_price - buy_order.price)
            trigger = "Current price triggered stoploss"
            sell_order = BitcoinTransaction(
                TransactionTypes.SELL,
                current_price,
                amount,
                volume,
                profit_or_loss,
                trigger,
            )
            print("New sell order placed:", sell_order)
            balance += amount
        # Check if investment goal has been reached
        elif balance + (current_price * buy_order.volume) >= GOAL:
            volume = buy_order.volume
            amount = current_price * volume
            # calculate the profit/loss incurred in this sell order
            profit_or_loss = volume * (current_price - buy_order.price)
            trigger = "Investment goal reached"
            sell_order = BitcoinTransaction(
                TransactionTypes.SELL,
                current_price,
                amount,
                volume,
                profit_or_loss,
                trigger,
            )
            print("New sell order placed:", sell_order)
            balance += amount
        # Check if predicted future price will fall below stoploss of current price, prevent possible loss
        elif predicted_price <= current_price * (1 - STOP_LOSS_PERCENTAGE):
            volume = buy_order.volume
            amount = current_price * volume
            # calculate the profit/loss incurred in this sell order
            profit_or_loss = volume * (current_price - buy_order.price)
            trigger = "Predicted future price triggered stoploss"
            sell_order = BitcoinTransaction(
                TransactionTypes.SELL,
                current_price,
                amount,
                volume,
                profit_or_loss,
                trigger,
            )
            print("New sell order placed:", sell_order)
            balance += amount
        else:
            print("Waiting for price to reach sell threshold")

    return buy_order, sell_order, balance


def configure_browser_state():
    display(
        IPython.core.display.HTML(
            """
    <canvas id="myChart"></canvas>
  """
        )
    )
    display(
        IPython.core.display.HTML(
            """
        <script src="https://cdn.jsdelivr.net/npm/chart.js@2.8.0"></script>
        <script>
          var ctx = document.getElementById('myChart').getContext('2d');
          var chart = new Chart(ctx, {
              // The type of chart we want to create
              type: 'line',

              // The data for our dataset
              data: {
                  labels: [getDateTime(-10), getDateTime(-20), getDateTime(-30),
                                  getDateTime(-40), getDateTime(-50), getDateTime(-60) ],
                  datasets: [{
                      label: 'Actual',
                      borderColor: 'rgb(255, 99, 132)',
                      data: [0,1,2,3,4,5]
                  }, 
                  {
                      label: 'Predicted',
                      borderColor: 'rgb(155, 199, 32)',
                      data: [0,1,2,3,4,5]
                  }]
              },

              // Configuration options go here
              options: { animation: {duration: 0} ,
                scales: {x: {
                           type: 'time',
                           time: { unit: 'minute',displayFormats: {minute: 'HH:mm'},tooltipFormat: 'HH:mm'},
                           title: {display: true, text: 'Date'}},
                         y: {
                           title: { display: true, text: 'value'}},
                         xAxes: [{ scaleLabel: { display: true, labelString: 'Timestamp [YYYY-MM-DD hh:mm:ss]'}}],
                        yAxes: [{scaleLabel: {display: true, labelString: 'BitCoin Price [USD $]'} }], },
                title: { display: true, text: 'Bitcoin Price - Realtime Prediction'}}});

          function getEpoch(offset_sec=0) {
             var now     = new Date(); 
             return Math.floor((now.getTime() - offset_sec*1000)/1000);}

          function getDateTime(offset_sec=0) {
             var now     = new Date(); 
             var numberOfMlSeconds = now.getTime() - offset_sec*1000;
             var update_now = new Date (numberOfMlSeconds);
             var year    = update_now.getFullYear();
             var month   = update_now.getMonth()+1; 
             var day     = update_now.getDate();
             var hour    = update_now.getHours();
             var minute  = update_now.getMinutes();
             var second  = update_now.getSeconds(); 
             if(month.toString().length == 1) {
                 month = '0'+month;}
             if(day.toString().length == 1) {
                 day = '0'+day;}   
             if(hour.toString().length == 1) {
                 hour = '0'+hour;}
             if(minute.toString().length == 1) {
                 minute = '0'+minute; }
             if(second.toString().length == 1) {
                 second = '0'+second;}   
             var dateTime = year+'-'+month+'-'+day+' '+hour+':'+minute+':'+second;   
             return dateTime;
          }

          function addData(value, value2){
            chart.data.labels.push(getDateTime())
            chart.data.datasets[0].data.push(value)
            chart.data.datasets[1].data.push(value2)
            // optional windowing
            if(chart.data.labels.length > 100) {
              chart.data.labels.shift()
              chart.data.datasets[0].data.shift()
              chart.data.datasets[1].data.shift() }

            chart.update();
          }
        </script>
        """
        )
    )


# Main program
def main():
    balance = INITIAL_BALANCE
    buy_order = None
    sell_order = None
    goal_reached = False

    # url = 'https://raw.githubusercontent.com/yetanotherpassword/COMS4507/main/BTC-USD.csv'
    # update this url to new dataset for future retraining.
    url = "https://raw.githubusercontent.com/AnsonCNS/COMS4507/main/BTC-USD_2023-05-21.csv"
    data = preprocess_data(url)
    last_date = datetime.strptime(data['Date'][data.shape[0]-1],'%Y-%m-%d')

    #separate the last 120 days to simulate as live daily data
    last_trainingdate = str(last_date+timedelta(days=-120))

    print("last_trainingdate="+last_trainingdate[0:10]+":")

    data_training = data[data['Date']< last_trainingdate[0:10]].copy()
    data_training
    print("Above is data_training")

    data_test = data[data['Date']< last_trainingdate[0:10]].copy()
    data_test
    print("Above  is data_test")

    live_data = data[data['Date'] >= last_trainingdate[0:10]].copy()

    training_data = data_training.drop(['Date'], axis = 1)
    training_data.head()
    print("Above is training_data.head())")

    scaler = MinMaxScaler()
    training_data = scaler.fit_transform(training_data)
    training_data

    X_train = [] 
    Y_train = []
    training_data.shape[0]
    for i in range(60, training_data.shape[0]):
      X_train.append(training_data[i-60:i])
      Y_train.append(training_data[i,0])
    X_train, Y_train = np.array(X_train), np.array(Y_train)
    X_train.shape

    model = train_lstm_model(X_train)
    history= model.fit(X_train, 
                       Y_train, 
                       epochs = 50, 
                       batch_size =50, 
                       validation_split=0.1)
    
    # Display training and Validation loss graph
    display_training_validation_loss(history)

    # Ready graph display
    configure_browser_state() 
    
    part_60_days = data_training.tail(60)
    df= part_60_days.append(live_data, ignore_index = True)
    days = df['Date']
    df = df.drop(['Date'], axis = 1)
    df.head()

    print("days=",days)
    inputs = scaler.transform(df) 
    inputs

    X_test = []
    Y_test = []
    Y_pred = -1
    print("inputs.shape[0]=",inputs.shape[0])
    for i in range (60, inputs.shape[0]):
        X_test.append(inputs[i-60:i]) 
        Y_test.append(inputs[i, 0])
        x1 = X_test[-1][-1]
        y1 = Y_test[-1]
        print("x1=",x1)
        print("y1=",y1)
        #if Y_pred != -1:
        #    model.train_on_batch(x1, y1)
        Y_pred = model.predict(np.array(X_test))
        print("days=",days[i])
        display(Javascript('addData('+str(Y_test[-1])+','+str(Y_pred[-1])+',"'+str(days[i])+'")'))

    plt.figure(figsize=(14,5))
    plt.plot(Y_test, color = 'red', label = 'Real Bitcoin Price')
    plt.plot(Y_pred, color = 'green', label = 'Predicted Bitcoin Price')
    plt.title('Bitcoin Price Prediction using RNN-LSTM')
    plt.xlabel('Time')
    plt.ylabel('Price')
    plt.legend()
    plt.show()

    ##FIXME
    # predict_lstm_price(model, data_test, data, days, scaler)

    # Trading Bot Section
    transaction_record = []
    profit_and_loss_record = []

    # FIXME the line below is for experimental demonstration, remove line to get real prices
    price = get_price()

    # keep running the bot if there is positive balance or an existing buy order has been placed.
    while (balance > 0 or buy_order) and not goal_reached:
        # FIXME
        # uncomment the following line to get real prices
        # current_price = get_price()

        # FIXME
        # the following line is for experimental demonstration, remove line to get real prices
        current_price = random.randint(int(price * (1 - 0.4)), int(price))

        if current_price is not None:
            print("Current price of BTC: $", current_price)
            predicted_price = predict_lstm_price(model, data_test, data, days, scaler)
            display(
                Javascript(
                    "addData(" + str(current_price) + "," + str(predicted_price) + ")"
                )
            )
            print("Predicted future price of BTC: $", predicted_price)
            buy_order, sell_order, balance = take_decision(
                current_price, predicted_price, balance, buy_order, sell_order
            )

            if sell_order:
                # record transaction
                transaction_record.append(sell_order)
                print("Sell order fulfilled. Profit: $", sell_order.profit_or_loss)
                profit_and_loss_record.append(
                    {sell_order.transaction_id: sell_order.profit_or_loss}
                )

                # reset orders
                buy_order = None
                sell_order = None

            elif buy_order:
                # record transaction
                transaction_record.append(buy_order)

            if balance >= GOAL:
                goal_reached = True
                print("Investment goal reached! Stop trading.")

            print("Remaining balance (USD): $", balance, "\n")

        else:
            print("Error getting price from CoinMarketCap API")

        time.sleep(INTERVALS)

    print("Transaction record:", transaction_record)
    print("Profit and Loss:", profit_and_loss_record)


if __name__ == "__main__":
    main()